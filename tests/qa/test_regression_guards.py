"""Regression guard tests — snapshot existing interfaces to detect breakage.

Marker: qa_regression
Some tests require PostgreSQL; config/column tests do not.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = PROJECT_ROOT / "scripts"
for _p in (str(PROJECT_ROOT), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from export_results import DETAIL_COLUMNS, OPERATIVE_COLUMNS, build_export_payload, write_export_bundle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_record(**overrides) -> dict:
    base = {
        "run_label": "regression-run",
        "fecha_inicio": "2026-04-11",
        "fecha_fin": "2026-04-11",
        "despacho_id": "050013103001",
        "despacho": "Juzgado 1 Civil Circuito Medellin",
        "publication_id": "PUB-001",
        "fecha_publicacion": "2026-04-11",
        "titulo_publicacion": "Estado 2026-04-11",
        "publication_url": "http://mock/pub/001",
        "pdf_label": "estado_planilla.pdf",
        "pdf_url": "http://mock/pdf/001.pdf",
        "pdf_path": "/tmp/pdfs/test.pdf",
        "pdf_fingerprint": "abc123",
        "pdf_page_number": 1,
        "row_index": 0,
        "raw_columns": [],
        "texto_fila_original": "row text",
        "radicado_raw": "2026-001",
        "radicado_normalizado": "2026-001",
        "tipo_proceso": "ejecutivo",
        "actuacion": "admite demanda",
        "demandante": "Juan Garcia",
        "demandado": "ACME S.A.S.",
        "anotacion": None,
        "revision_manual": "No",
        "parse_mode": "column_coordinates",
        "parse_confidence": 0.95,
        "decision": "accepted",
        "match_reason": "process_type",
        "process_type_match": "ejecutivo",
        "actuacion_match": "admite demanda",
        "process_type_confidence": 0.95,
        "actuacion_confidence": 0.92,
        "blacklisted": False,
        "blacklist_match": None,
        "draft_id": None,
        "draft_status": None,
        "draft_email_to": None,
    }
    base.update(overrides)
    return base


def _meta() -> dict:
    return {
        "fecha_inicio": "2026-04-11",
        "fecha_fin": "2026-04-11",
        "despachos_total": 1,
        "publications_total": 1,
        "pdfs_total": 1,
        "enrichment_enabled": False,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.qa_regression
def test_no_db_output_format_shape():
    """build_export_payload sin enrichment: payload tiene summary, pdf_summaries, records, operative_records."""
    records = [_base_record()]
    payload = build_export_payload("regression-run", _meta(), records)

    assert "summary" in payload, "Missing 'summary' key in export payload"
    assert "pdf_summaries" in payload, "Missing 'pdf_summaries' key in export payload"
    assert "records" in payload, "Missing 'records' key in export payload"
    assert "operative_records" in payload, "Missing 'operative_records' key in export payload"


@pytest.mark.qa_regression
def test_file_export_works_with_db_active(tmp_path):
    """write_export_bundle produce exactamente 7 archivos (4 JSON + 3 CSV)."""
    records = [_base_record()]
    payload = build_export_payload("regression-run", _meta(), records)
    export_dir = tmp_path / "exports"
    outputs = write_export_bundle(export_dir, payload)

    assert len(outputs) == 7, f"Expected 7 exported files, got {len(outputs)}: {list(outputs.keys())}"

    json_files = [k for k in outputs if k.endswith("_json")]
    csv_files = [k for k in outputs if k.endswith("_csv")]
    assert len(json_files) == 4, f"Expected 4 JSON outputs, got {len(json_files)}"
    assert len(csv_files) == 3, f"Expected 3 CSV outputs, got {len(csv_files)}"

    for path in outputs.values():
        assert Path(path).exists(), f"Export file not created: {path}"


@pytest.mark.qa_regression
def test_operative_columns_stable():
    """OPERATIVE_COLUMNS tiene exactamente las columnas esperadas (snapshot)."""
    expected = [
        "run_label",
        "fecha_inicio",
        "fecha_fin",
        "despacho_id",
        "despacho",
        "fecha_publicacion",
        "titulo_publicacion",
        "pdf_path",
        "radicado_normalizado",
        "tipo_proceso",
        "actuacion",
        "demandante",
        "demandado",
        "decision",
        "match_reason",
        "revision_manual",
        "process_type_match",
        "actuacion_match",
        "match_camara",
        "emails_encontrados",
        "draft_id",
        "draft_status",
        "draft_email_to",
        "blacklisted",
        "blacklist_match",
    ]
    assert OPERATIVE_COLUMNS == expected, (
        f"OPERATIVE_COLUMNS changed!\nExpected: {expected}\nGot: {OPERATIVE_COLUMNS}"
    )


@pytest.mark.qa_regression
def test_detail_columns_stable():
    """DETAIL_COLUMNS tiene exactamente las columnas esperadas (snapshot)."""
    expected = [
        "run_label",
        "fecha_inicio",
        "fecha_fin",
        "despacho_id",
        "despacho",
        "publication_id",
        "fecha_publicacion",
        "titulo_publicacion",
        "publication_url",
        "pdf_label",
        "pdf_url",
        "pdf_path",
        "pdf_fingerprint",
        "pdf_page_number",
        "row_index",
        "radicado_raw",
        "radicado_normalizado",
        "tipo_proceso",
        "actuacion",
        "demandante",
        "demandado",
        "anotacion",
        "revision_manual",
        "parse_mode",
        "parse_confidence",
        "decision",
        "match_reason",
        "process_type_match",
        "actuacion_match",
        "process_type_confidence",
        "actuacion_confidence",
        "texto_fila_original",
    ]
    assert DETAIL_COLUMNS == expected, (
        f"DETAIL_COLUMNS changed!\nExpected: {expected}\nGot: {DETAIL_COLUMNS}"
    )


@pytest.mark.qa_regression
def test_enriched_no_legacy_fields():
    """enrich_record_from_db produce match_camara, NO match_2023/match_2025/match_total (legacy).

    Uses source inspection so the test runs without DATABASE_URL.
    """
    import inspect
    from enrich_contacts import enrich_record_from_db

    source = inspect.getsource(enrich_record_from_db)

    assert "match_camara" in source, "match_camara key missing from enrich_record_from_db"
    for legacy_key in ("match_2023", "match_2025", "match_total"):
        assert legacy_key not in source, (
            f"Legacy key {legacy_key!r} found in enrich_record_from_db — "
            "DB enrichment should not set legacy file-based fields"
        )


@pytest.mark.qa_regression
def test_run_pipeline_signature():
    """inspect.signature(run_pipeline) tiene param 'no_db' con default False."""
    import run_search

    sig = inspect.signature(run_search.run_pipeline)
    assert "no_db" in sig.parameters, "run_pipeline is missing 'no_db' parameter"
    assert sig.parameters["no_db"].default is False, (
        f"run_pipeline 'no_db' default should be False, got: {sig.parameters['no_db'].default!r}"
    )
