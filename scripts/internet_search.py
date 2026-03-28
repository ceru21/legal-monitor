"""
internet_search.py — Búsqueda de NIT, email y teléfono de empresas en internet.

Estrategia:
  1. Búsqueda 1: "{nombre}" NIT Colombia → extraer NIT con regex
  2. Búsqueda 2: "{nombre}" "{NIT}" email contacto → visitar top 2 páginas → extraer email/tel

Scoring de confianza para verificar que es la empresa correcta:
  - Nombre normalizado coincide exactamente → +60
  - Nombre normalizado coincide parcialmente (>85%) → +30
  - Fuente oficial (supersociedades, rues, dian) → +20
  - Dominio de la empresa → +15
  - Directorio genérico → +5
  - Ciudad coincide → +10
  - NIT en múltiples fuentes → +10

Umbral mínimo para aceptar: 70 puntos
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9",
}

FUENTES_OFICIALES = {
    "supersociedades.gov.co",
    "rues.org.co",
    "datos.gov.co",
    "dian.gov.co",
}

# Regex para NIT colombiano: 9 dígitos + dígito verificador
NIT_RE = re.compile(r'\b(\d{6,10})[.\-\s]?(\d)\b')
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
PHONE_RE = re.compile(r'(?:\+57[\s\-]?)?(?:3\d{2}[\s\-]?\d{3}[\s\-]?\d{4}|[26]\d{6,7})')


# ---------------------------------------------------------------------------
# Normalización
# ---------------------------------------------------------------------------

def _remove_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def normalize(text: str | None) -> str:
    if not text:
        return ""
    t = text.lower()
    t = _remove_accents(t)
    t = re.sub(r'[^a-z0-9\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def name_similarity(a: str, b: str) -> float:
    """Similitud entre dos nombres normalizados (0-1)."""
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------

@dataclass
class EnrichResult:
    nombre_buscado: str
    nit: str | None = None
    email: str | None = None
    telefono: str | None = None
    pagina_web: str | None = None
    fuente: str | None = None
    score: int = 0
    confianza: str = "baja"      # alta / media / baja / no_encontrado
    detalle_score: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nombre_buscado": self.nombre_buscado,
            "nit": self.nit,
            "email": self.email,
            "telefono": self.telefono,
            "pagina_web": self.pagina_web,
            "fuente": self.fuente,
            "score": self.score,
            "confianza": self.confianza,
        }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def compute_score(
    nombre_buscado: str,
    nombre_encontrado: str,
    fuente_url: str,
    ciudad_proceso: str | None = None,
    ciudad_encontrada: str | None = None,
    nit_multifuente: bool = False,
    config: dict | None = None,
) -> tuple[int, dict]:
    cfg = config or {}
    pts: dict[str, int] = {}

    # Nombre — normalizar ambos antes de comparar
    norm_buscado = normalize(nombre_buscado)
    norm_encontrado = normalize(nombre_encontrado)
    sim = name_similarity(norm_buscado, norm_encontrado)
    # Considerar exacto si el nombre buscado normalizado está contenido en el encontrado
    # o viceversa (cubre casos donde el encontrado tiene sufijo corporativo adicional)
    if sim >= 0.95 or norm_buscado in norm_encontrado or norm_encontrado in norm_buscado:
        pts["nombre_exacto"] = cfg.get("score_nombre_exacto", 60)
    elif sim >= 0.85:
        pts["nombre_parcial"] = cfg.get("score_nombre_parcial", 30)

    # Fuente
    domain = urlparse(fuente_url).netloc.lower().lstrip("www.")
    if any(domain == f or domain.endswith("." + f) for f in FUENTES_OFICIALES):
        pts["fuente_oficial"] = cfg.get("score_fuente_oficial", 20)
    else:
        # Heurística: si el dominio contiene palabras del nombre → página propia
        nombre_norm = normalize(nombre_buscado)
        domain_norm = normalize(domain)
        words = [w for w in nombre_norm.split() if len(w) > 3]
        if any(w in domain_norm for w in words):
            pts["fuente_propia"] = cfg.get("score_fuente_propia", 15)
        else:
            pts["fuente_directorio"] = cfg.get("score_fuente_directorio", 5)

    # Ciudad
    if ciudad_proceso and ciudad_encontrada:
        if normalize(ciudad_proceso) in normalize(ciudad_encontrada):
            pts["ciudad_coincide"] = cfg.get("score_ciudad_coincide", 10)

    # NIT en múltiples fuentes
    if nit_multifuente:
        pts["nit_multifuente"] = cfg.get("score_nit_multifuente", 10)

    total = sum(pts.values())
    return total, pts


# ---------------------------------------------------------------------------
# Búsqueda en internet
# ---------------------------------------------------------------------------

SEARCH_URL = "https://www.google.com/search?q={query}&hl=es&num=5"
DDG_URL = "https://html.duckduckgo.com/html/?q={query}"


def _search(query: str, throttle: float = 3.0) -> list[dict[str, str]]:
    """
    Busca en DuckDuckGo y retorna lista de {title, url, snippet}.
    Fallback a Google si DDG falla.
    """
    time.sleep(throttle)
    results = []

    try:
        url = DDG_URL.format(query=quote_plus(query))
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select(".result__a")[:5]:
                href = a.get("href", "")
                title = a.get_text(strip=True)
                snippet_el = a.find_next(".result__snippet")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                if href and title:
                    results.append({"title": title, "url": href, "snippet": snippet})
    except Exception as e:
        logger.warning("DDG search failed: %s", e)

    if not results:
        # Fallback Google
        try:
            url = SEARCH_URL.format(query=quote_plus(query))
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                for g in soup.select("div.g")[:5]:
                    a_tag = g.select_one("a")
                    if not a_tag:
                        continue
                    href = a_tag.get("href", "")
                    title = g.select_one("h3")
                    snippet = g.select_one(".VwiC3b")
                    results.append({
                        "title": title.get_text() if title else "",
                        "url": href,
                        "snippet": snippet.get_text() if snippet else "",
                    })
        except Exception as e:
            logger.warning("Google search failed: %s", e)

    return results


def _fetch_page(url: str, throttle: float = 2.0) -> str:
    """Descarga una página y retorna el texto plano."""
    time.sleep(throttle)
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            # Eliminar scripts y styles
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            return soup.get_text(separator=" ", strip=True)
    except Exception as e:
        logger.debug("Fetch failed for %s: %s", url, e)
    return ""


def _extract_nit(text: str) -> str | None:
    """Extrae el primer NIT válido del texto."""
    for match in NIT_RE.finditer(text):
        digits = match.group(1)
        if 7 <= len(digits) <= 10:
            return f"{digits}-{match.group(2)}"
    return None


def _extract_emails(text: str) -> list[str]:
    emails = EMAIL_RE.findall(text)
    # Filtrar emails inválidos o genéricos
    blacklist = {"example.com", "correo.com", "email.com", "dominio.com"}
    return [
        e.lower() for e in emails
        if not any(b in e.lower() for b in blacklist)
    ]


def _extract_phones(text: str) -> list[str]:
    return list(set(PHONE_RE.findall(text)))


# ---------------------------------------------------------------------------
# Enriquecimiento principal
# ---------------------------------------------------------------------------

def enrich_empresa(
    nombre: str,
    ciudad_proceso: str | None = None,
    throttle_search: float = 3.0,
    throttle_page: float = 2.0,
    score_minimo: int = 70,
    score_alta: int = 90,
    config: dict | None = None,
) -> EnrichResult:
    """
    Busca NIT, email y teléfono para una empresa.
    Retorna EnrichResult con score de confianza.
    """
    result = EnrichResult(nombre_buscado=nombre)
    nit = None
    nit_sources: list[str] = []
    best_score = 0
    best_source_url = ""
    best_nombre_encontrado = ""

    # ── Paso 1: Buscar NIT ──
    query_nit = f'"{nombre}" NIT Colombia'
    results_nit = _search(query_nit, throttle=throttle_search)

    for res in results_nit[:3]:
        # Extraer NIT del snippet o título
        combined = f"{res['title']} {res['snippet']}"
        found_nit = _extract_nit(combined)
        if found_nit:
            if not nit:
                nit = found_nit
                nit_sources.append(res["url"])
            elif found_nit == nit:
                nit_sources.append(res["url"])  # confirmado en otra fuente

        # Scoring del resultado
        score, detail = compute_score(
            nombre_buscado=nombre,
            nombre_encontrado=res["title"],
            fuente_url=res["url"],
            ciudad_proceso=ciudad_proceso,
            config=config,
            nit_multifuente=len(nit_sources) > 1,
        )
        if score > best_score:
            best_score = score
            best_source_url = res["url"]
            best_nombre_encontrado = res["title"]
            result.detalle_score = detail
            result.pagina_web = res["url"]

    # ── Paso 2: Buscar email con NIT ──
    if nit:
        query_email = f'"{nombre}" "{nit}" email contacto'
    else:
        query_email = f'"{nombre}" email contacto Colombia'

    results_email = _search(query_email, throttle=throttle_search)

    emails_found: list[str] = []
    phones_found: list[str] = []

    for res in results_email[:2]:
        # Primero intentar extraer del snippet
        combined = f"{res['title']} {res['snippet']}"
        emails_found.extend(_extract_emails(combined))
        phones_found.extend(_extract_phones(combined))

        # Si no hay email en snippet, visitar la página
        if not emails_found:
            page_text = _fetch_page(res["url"], throttle=throttle_page)
            if page_text:
                emails_found.extend(_extract_emails(page_text))
                phones_found.extend(_extract_phones(page_text))

                # Re-scoring con la página visitada
                score, detail = compute_score(
                    nombre_buscado=nombre,
                    nombre_encontrado=res["title"],
                    fuente_url=res["url"],
                    ciudad_proceso=ciudad_proceso,
                    config=config,
                    nit_multifuente=len(nit_sources) > 1,
                )
                if score > best_score:
                    best_score = score
                    best_source_url = res["url"]
                    result.detalle_score = detail
                    result.pagina_web = res["url"]

        if emails_found:
            break  # Con un email es suficiente para esta empresa

    # ── Calcular score final ──
    final_score, _ = compute_score(
        nombre_buscado=nombre,
        nombre_encontrado=best_nombre_encontrado,
        fuente_url=best_source_url,
        ciudad_proceso=ciudad_proceso,
        config=config,
        nit_multifuente=len(nit_sources) > 1,
    )
    result.score = final_score
    result.nit = nit
    result.email = emails_found[0] if emails_found else None
    result.telefono = phones_found[0] if phones_found else None
    result.fuente = best_source_url or None

    # ── Confianza ──
    if final_score >= score_alta and result.email:
        result.confianza = "alta"
    elif final_score >= score_minimo and result.email:
        result.confianza = "media"
    elif final_score >= score_minimo and not result.email:
        result.confianza = "nit_only"  # Encontró NIT pero no email
    else:
        result.confianza = "no_encontrado"
        result.email = None  # No aceptar si el score es bajo

    logger.info(
        "enrich '%s' → score=%d confianza=%s nit=%s email=%s",
        nombre, final_score, result.confianza, result.nit, result.email
    )
    return result
