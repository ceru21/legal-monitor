"""
blacklist.py — Filtro de empresas excluidas del outreach.

Matching exacto normalizado:
  - Minúsculas
  - Sin tildes ni caracteres especiales
  - Sin sufijos corporativos (s.a.s, ltda, s.a, s en c, etc.)
  - Sin espacios extra

El campo 'demandado' normalizado debe ser IGUAL a la entrada de la blacklist.
Matching parcial no aplica — "banco" no excluye "banco de bogota" a menos que
"banco de bogota" esté explícitamente en la lista.

Uso:
    from blacklist import BlacklistFilter
    bf = BlacklistFilter.from_yaml("config/blacklist.yaml")
    records = bf.apply(records)
    # Los registros tienen 'blacklisted': True/False y 'blacklist_match': str|None
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

CORP_SUFFIXES = [
    r"\bs\.?a\.?s\.?\b",
    r"\bs\.?a\.?\b",
    r"\bltda\.?\b",
    r"\blimitada\b",
    r"\bs\s+en\s+c\.?\b",
    r"\bs\.?c\.?a\.?\b",
    r"\by\s+cia\.?\b",
    r"\by\s+compa[nñ]ia\b",
    r"\bsociedad\s+anonima\b",
    r"\bsociedad\s+por\s+acciones\s+simplificada\b",
    r"\be\.?u\.?\b",
    r"\bempresa\s+unipersonal\b",
]

CORP_SUFFIX_RE = re.compile("|".join(CORP_SUFFIXES), re.IGNORECASE)


def _remove_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def normalize(value: str | None) -> str:
    """Normaliza un nombre para comparación exacta."""
    if not value:
        return ""
    text = value.lower()
    text = _remove_accents(text)
    text = CORP_SUFFIX_RE.sub(" ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class BlacklistFilter:
    def __init__(self, entries: list[str]) -> None:
        # Normalizar las entradas de la blacklist al momento de cargar
        self._entries: set[str] = {normalize(e) for e in entries if e}

    @classmethod
    def from_yaml(cls, path: str | Path) -> "BlacklistFilter":
        path = Path(path)
        if not path.exists():
            return cls([])
        if not _HAS_YAML:
            # Fallback: leer líneas simples si yaml no está disponible
            entries = [
                line.strip().lstrip("- ").strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
                and not line.strip().startswith("empresas:")
            ]
            return cls(entries)
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(data.get("empresas", []))

    def is_blacklisted(self, demandado: str | None) -> tuple[bool, str | None]:
        """
        Retorna (True, entrada_match) si el demandado está en la blacklist.
        Matching exacto sobre texto normalizado.
        """
        norm = normalize(demandado)
        if not norm:
            return False, None
        if norm in self._entries:
            return True, norm
        return False, None

    def apply(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Agrega 'blacklisted' (bool) y 'blacklist_match' (str|None) a cada registro.
        No elimina registros — solo los marca.
        """
        result = []
        for record in records:
            blacklisted, match = self.is_blacklisted(record.get("demandado"))
            result.append({
                **record,
                "blacklisted": blacklisted,
                "blacklist_match": match,
            })
        return result
