from __future__ import annotations

import re
from datetime import date


def validate_date(value: str) -> str:
    """Validate and return a YYYY-MM-DD date string; raise ValueError if invalid."""
    try:
        date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid date '{value}'. Expected format: YYYY-MM-DD")
    return value


_DESPACHO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,50}$")


def validate_despacho_id(value: str) -> str:
    """Validate a despacho ID (alphanumeric, underscores, hyphens, max 50 chars)."""
    if not _DESPACHO_ID_RE.match(value):
        raise ValueError(
            f"Invalid despacho_id '{value}'. "
            "Only letters, digits, underscores and hyphens are allowed (max 50 chars)."
        )
    return value


_CONN_STR_RE = re.compile(r"\w+://[^\s]+")


def sanitize_exception(exc: Exception) -> str:
    """Return a sanitized string representation of an exception.

    Redacts connection strings and truncates to 200 characters.
    """
    raw = str(exc)
    sanitized = _CONN_STR_RE.sub("[connection-string-redacted]", raw)
    if len(sanitized) > 200:
        sanitized = sanitized[:200] + "…"
    return sanitized
