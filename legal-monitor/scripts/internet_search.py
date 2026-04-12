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
from urllib.parse import quote_plus, unquote, urlparse

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

DDG_URL = "https://html.duckduckgo.com/html/?q={query}"
DATOS_GOV_API = "https://www.datos.gov.co/resource/c82u-588k.json"


def _lookup_nit(nombre: str) -> str | None:
    """
    Consulta el dataset de registro mercantil en datos.gov.co para obtener el NIT.
    API pública Socrata — sin bloqueos ni scraping.
    """
    try:
        nombre_norm = normalize(nombre)
        # Búsqueda por palabras clave del nombre
        words = [w for w in nombre_norm.split() if len(w) > 3]
        if not words:
            return None
        like_query = "%" + "%".join(words[:3]) + "%"
        params = {
            "$where": f"razon_social like '{like_query}'",
            "$limit": "5",
        }
        r = requests.get(DATOS_GOV_API, params=params, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        if not data:
            return None
        # Elegir el resultado con mayor similitud de nombre
        best = max(data, key=lambda x: name_similarity(nombre, x.get("razon_social", "")))
        sim = name_similarity(nombre, best.get("razon_social", ""))
        if sim < 0.75:
            return None
        nit = best.get("numero_identificacion") or best.get("nit")
        dv = best.get("digito_verificacion", "")
        if nit:
            return f"{nit}-{dv}" if dv else str(nit)
    except Exception as e:
        logger.debug("NIT lookup failed for '%s': %s", nombre, e)
    return None


def _ddg_search(query: str, throttle: float = 3.0) -> list[dict[str, str]]:
    """
    Busca en DuckDuckGo SIN comillas (evita detección de bot).
    Retorna lista de {title, url}.
    """
    time.sleep(throttle)
    results = []
    try:
        url = DDG_URL.format(query=quote_plus(query))
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select(".result__a")[:5]:
                raw_href = a.get("href", "")
                # DDG redirecciona via /l/?uddg=<url>
                m = re.search(r'uddg=([^&]+)', raw_href)
                href = unquote(m.group(1)) if m else raw_href
                title = a.get_text(strip=True)
                snippet_el = a.find_next(".result__snippet")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                if href and title and href.startswith("http"):
                    results.append({"title": title, "url": href, "snippet": snippet})
    except Exception as e:
        logger.warning("DDG search failed: %s", e)
    return results


def _fetch_page(url: str, throttle: float = 2.0) -> str:
    """Descarga una página y retorna el texto plano completo."""
    time.sleep(throttle)
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            return soup.get_text(separator=" ", strip=True)
    except Exception as e:
        logger.debug("Fetch failed for %s: %s", url, e)
    return ""


CONTACT_KEYWORDS = re.compile(
    r'\b(contacto|contact|atencion|atención|comunicacion|comunicación|'
    r'info|gerencia|administracion|administración|ventas|comercial|'
    r'servicio|soporte|escritorio)\b',
    re.IGNORECASE
)

CONTACT_URL_KEYWORDS = ["contacto", "contact", "nosotros", "about", "atencion", "info"]


def _score_email_proximity(text: str, email: str) -> int:
    """
    Da un score a un email según su proximidad a palabras de contacto.
    Retorna 0-100.
    """
    idx = text.lower().find(email.lower())
    if idx == -1:
        return 0
    # Ventana de 200 chars alrededor del email
    window = text[max(0, idx-200):idx+200].lower()
    matches = len(CONTACT_KEYWORDS.findall(window))
    return min(matches * 25, 100)


def _extract_best_emails(text: str, max_emails: int = 5) -> list[str]:
    """
    Extrae emails del texto ordenados por proximidad a palabras de contacto.
    Filtra emails corporativos genéricos no deseados.
    """
    raw_emails = list(dict.fromkeys(EMAIL_RE.findall(text)))  # dedup orden
    # Filtrar dominios inválidos y emails de sistema
    blacklist_domains = {
        "example.com", "correo.com", "email.com", "dominio.com",
        "sentry.io", "wixpress.com", "amazonaws.com", "cloudfront.net",
        "google.com", "gmail.com", "hotmail.com", "yahoo.com",
        # Directorios que tienen emails de contacto propios, no de la empresa
        "pghseguros.com", "informacolombia.com", "registronit.com",
        "empresite.com", "empresite.eleconomistaamerica.co",
    }
    filtered = [
        e.lower() for e in raw_emails
        if not any(b in e.lower() for b in blacklist_domains)
        and len(e) < 80
    ]
    # Ordenar por proximidad a palabras de contacto
    scored = [(e, _score_email_proximity(text, e)) for e in filtered]
    scored.sort(key=lambda x: -x[1])
    return [e for e, _ in scored[:max_emails]]


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
    best_score = 0
    best_source_url = ""
    best_nombre_encontrado = nombre

    # ── Paso 1: NIT desde datos.gov.co (API oficial, sin bloqueos) ──
    nit = _lookup_nit(nombre)
    if nit:
        logger.debug("NIT encontrado via datos.gov.co: %s → %s", nombre, nit)
        best_score = max(best_score, 70)  # Fuente oficial da confianza base

    # ── Paso 2: Buscar páginas con NIT + nombre en DDG (sin comillas) ──
    nit_clean = nit.split("-")[0] if nit else ""
    if nit_clean:
        query_email = f"{nombre} {nit_clean} contacto Colombia"
    else:
        query_email = f"{nombre} contacto email Colombia"

    ddg_results = _ddg_search(query_email, throttle=throttle_search)

    # Priorizar URLs de contacto
    ddg_results.sort(
        key=lambda r: 0 if any(kw in r["url"].lower() for kw in CONTACT_URL_KEYWORDS) else 1
    )

    emails_found: list[str] = []
    phones_found: list[str] = []

    for res in ddg_results[:3]:
        # Scoring del resultado
        score, detail = compute_score(
            nombre_buscado=nombre,
            nombre_encontrado=res["title"],
            fuente_url=res["url"],
            ciudad_proceso=ciudad_proceso,
            config=config,
            nit_multifuente=bool(nit),
        )
        if score > best_score:
            best_score = score
            best_source_url = res["url"]
            best_nombre_encontrado = res["title"]
            result.detalle_score = detail
            result.pagina_web = res["url"]

        # Visitar la página y extraer emails/teléfonos
        page_text = _fetch_page(res["url"], throttle=throttle_page)
        if page_text:
            page_emails = _extract_best_emails(page_text)
            page_phones = _extract_phones(page_text)
            for e in page_emails:
                if e not in emails_found:
                    emails_found.append(e)
            phones_found.extend(p for p in page_phones if p not in phones_found)

        if emails_found:
            break  # Con al menos un email paramos

    # ── Score final ──
    final_score, _ = compute_score(
        nombre_buscado=nombre,
        nombre_encontrado=best_nombre_encontrado,
        fuente_url=best_source_url,
        ciudad_proceso=ciudad_proceso,
        config=config,
        nit_multifuente=bool(nit),
    )
    # Si encontramos NIT via API oficial, el score base es al menos 70
    if nit and final_score < 70:
        final_score = 70

    result.score = final_score
    result.nit = nit
    result.email = emails_found[0] if emails_found else None
    result.telefono = phones_found[0] if phones_found else None
    result.fuente = best_source_url or (DATOS_GOV_API if nit else None)

    # ── Confianza ──
    if final_score >= score_alta and result.email:
        result.confianza = "alta"
    elif final_score >= score_minimo and result.email:
        result.confianza = "media"
    elif result.nit and final_score >= 60:
        # Encontró NIT aunque no email — vale para el Sheet de pendientes
        result.confianza = "nit_only"
    else:
        result.confianza = "no_encontrado"
        result.email = None  # No aceptar si el score es bajo

    logger.info(
        "enrich '%s' → score=%d confianza=%s nit=%s email=%s",
        nombre, final_score, result.confianza, result.nit, result.email
    )
    return result
