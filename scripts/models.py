from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Publication:
    publication_id: str | None
    despacho: str | None
    fecha_publicacion: str | None
    titulo_publicacion: str | None
    publication_url: str | None
    pdf_url: str | None
    portal_page_number: int = 1
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DetailDocument:
    label: str
    url: str
    is_primary_candidate: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedRow:
    pdf_fingerprint: str | None
    pdf_page_number: int
    row_index: int
    raw_columns: list[str]
    texto_fila_original: str
    radicado_raw: str | None = None
    radicado_normalizado: str | None = None
    demandante: str | None = None
    demandado: str | None = None
    tipo_proceso: str | None = None
    actuacion: str | None = None
    anotacion: str | None = None
    parse_mode: str = "failed"
    parse_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MatchDecision:
    decision: str
    match_reason: str
    process_type_match: str | None = None
    actuacion_match: str | None = None
    process_type_confidence: float = 0.0
    actuacion_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunSummary:
    fecha_ejecucion: str
    despachos_consultados: int
    publicaciones_encontradas: int
    pdfs_descargados: int
    pdfs_parseados_ok: int
    pdfs_con_error: int
    filas_detectadas: int
    filas_matcheadas: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
