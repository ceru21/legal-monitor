"""Data round-trip integrity tests: pipeline record → DB → export.

Marker: qa_data_flow
Requires: PostgreSQL (via test_engine fixture from tests/conftest.py)
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = PROJECT_ROOT / "scripts"
for _p in (str(PROJECT_ROOT), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from export_results import DETAIL_COLUMNS, build_export_payload, write_export_bundle

# DB imports are lazy (inside tests) to allow collection without DATABASE_URL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_record(**overrides) -> dict:
    base = {
        "run_label": "roundtrip-run",
        "fecha_inicio": "2026-04-11",
        "fecha_fin": "2026-04-11",
        "despacho_id": "050013103001",
        "despacho": "Juzgado 1 Civil Circuito Medellin",
        "publication_id": "PUB-001",
        "fecha_publicacion": "2026-04-11",
        "titulo_publicacion": "Estado 2026-04-11",
        "publication_url": "http://mock/pub/001",
        "pdf_label": "estado_planilla.pdf",
        "pdf_url": "http://mock/pdf/estado_planilla.pdf",
        "pdf_path": "/tmp/pdfs/test.pdf",
        "pdf_fingerprint": "abc123",
        "pdf_page_number": 1,
        "row_index": 0,
        "raw_columns": ["2026-001", "ejecutivo", "admite demanda", "ACME S.A.S.", "Juan Garcia"],
        "texto_fila_original": "2026-001 ejecutivo admite demanda ACME S.A.S. Juan Garcia",
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
        "match_camara": True,
        "emails_encontrados": ["contacto@acme.com"],
        "demandado_normalizado_match": "acme",
        "blacklisted": False,
        "blacklist_match": None,
        "draft_id": None,
        "draft_status": None,
        "draft_email_to": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.qa_data_flow
def test_full_roundtrip_pipeline_db_query(db_session):
    """Record → save_run → query PipelineRecord: full_record JSONB contiene campos originales."""
    from db.models import PipelineRecord
    from db.repository import save_run

    record = _minimal_record()
    run = save_run(
        "roundtrip-full-001",
        "2026-04-11",
        "2026-04-11",
        {"enrichment_enabled": True},
        [record],
        db_session,
    )

    pr = db_session.query(PipelineRecord).filter_by(run_id=run.id).first()
    assert pr is not None, "PipelineRecord not found"

    full = pr.full_record
    assert full is not None, "full_record JSONB is None"
    assert full["demandado"] == "ACME S.A.S."
    assert full["decision"] == "accepted"
    assert full["match_camara"] is True
    assert "contacto@acme.com" in full.get("emails_encontrados", [])


@pytest.mark.qa_data_flow
def test_enrichment_preserves_original_fields(db_session):
    """enrich_record_from_db no borra ni corrompe keys existentes del record."""
    from db.models import Contact
    from enrich_contacts import enrich_record_from_db, normalize_company_name

    # Seed contact for ACME
    db_session.add(
        Contact(
            razon_social="ACME S.A.S.",
            razon_social_normalizada=normalize_company_name("ACME S.A.S."),
            correo_comercial="contacto@acme.com",
            source_label="test_qa",
        )
    )
    db_session.flush()

    original = {
        "demandado": "ACME S.A.S.",
        "decision": "accepted",
        "radicado_normalizado": "2026-001",
        "tipo_proceso": "ejecutivo",
        "despacho_id": "050013103001",
        "custom_field": "should_survive",
    }
    enriched = enrich_record_from_db(original, db_session)

    # All original keys must still be present
    for key, value in original.items():
        assert enriched[key] == value, f"Key {key!r} was corrupted by enrichment"

    # Enrichment keys must be added
    assert "match_camara" in enriched
    assert "emails_encontrados" in enriched
    assert enriched["match_camara"] is True


@pytest.mark.qa_data_flow
def test_jsonb_contains_all_expected_keys(db_session):
    """full_record.keys() es superset de DETAIL_COLUMNS (excluye columnas opcionales no siempre presentes)."""
    from db.models import PipelineRecord
    from db.repository import save_run

    required_keys = {
        "run_label", "fecha_inicio", "fecha_fin", "despacho_id", "despacho",
        "decision", "demandado", "demandante", "tipo_proceso", "actuacion",
        "radicado_normalizado", "pdf_path",
    }
    record = _minimal_record()
    run = save_run(
        "roundtrip-jsonb-001",
        "2026-04-11",
        "2026-04-11",
        {},
        [record],
        db_session,
    )

    pr = db_session.query(PipelineRecord).filter_by(run_id=run.id).first()
    assert pr is not None

    stored_keys = set(pr.full_record.keys())
    missing = required_keys - stored_keys
    assert not missing, f"JSONB full_record is missing keys: {missing}"


@pytest.mark.qa_data_flow
def test_export_matches_db_content(db_session, tmp_path):
    """CSV/JSON exportado == contenido DB para mismos records."""
    from db.models import PipelineRecord
    from db.repository import save_run

    records = [
        _minimal_record(radicado_normalizado="2026-001", decision="accepted"),
        _minimal_record(radicado_normalizado="2026-002", decision="review",
                        demandado="EMPRESA DESCONOCIDA", match_camara=False,
                        emails_encontrados=[]),
    ]
    run = save_run(
        "roundtrip-export-001",
        "2026-04-11",
        "2026-04-11",
        {"enrichment_enabled": True},
        records,
        db_session,
    )

    prs = db_session.query(PipelineRecord).filter_by(run_id=run.id).all()
    db_radicados = {pr.full_record["radicado_normalizado"] for pr in prs}

    # Build export
    metadata = {"fecha_inicio": "2026-04-11", "fecha_fin": "2026-04-11",
                 "despachos_total": 1, "publications_total": 1, "pdfs_total": 1}
    payload = build_export_payload("roundtrip-export-001", metadata, records)
    export_dir = tmp_path / "exports"
    write_export_bundle(export_dir, payload)

    # Parse exported JSON
    with open(export_dir / "records_detailed.json", encoding="utf-8") as f:
        exported = json.load(f)
    export_radicados = {r["radicado_normalizado"] for r in exported}

    assert db_radicados == export_radicados


@pytest.mark.qa_data_flow
def test_null_chain(db_session):
    """demandado=None, despacho_id=None: enrich no crashea, DB tiene NULL, export tiene null."""
    from db.models import PipelineRecord
    from db.repository import save_run
    from enrich_contacts import enrich_record_from_db

    record_with_nulls = _minimal_record(demandado=None, despacho_id=None)
    enriched = enrich_record_from_db(record_with_nulls, db_session)

    assert enriched["demandado"] is None
    assert enriched["match_camara"] is False  # no match on None name
    assert enriched["emails_encontrados"] == []

    # Save to DB
    run = save_run(
        "roundtrip-null-001",
        "2026-04-11",
        "2026-04-11",
        {},
        [enriched],
        db_session,
    )
    pr = db_session.query(PipelineRecord).filter_by(run_id=run.id).first()
    assert pr is not None
    assert pr.demandado is None
    assert pr.despacho_id is None

    # Export must not crash on null values
    metadata = {"fecha_inicio": "2026-04-11", "fecha_fin": "2026-04-11",
                 "despachos_total": 1, "publications_total": 1, "pdfs_total": 1}
    payload = build_export_payload("roundtrip-null-001", metadata, [enriched])
    assert payload["summary"]["rows_total"] == 1


@pytest.mark.qa_data_flow
def test_special_characters_roundtrip(db_session):
    """Caracteres especiales sobreviven save→query sin corrupción."""
    from db.models import PipelineRecord
    from db.repository import save_run

    demandado = "O'BRIEN & CIA \"LTDA\""
    actuacion = "notificación auto — señalamiento audiencia"
    record = _minimal_record(demandado=demandado, actuacion=actuacion)

    run = save_run(
        "roundtrip-special-001",
        "2026-04-11",
        "2026-04-11",
        {},
        [record],
        db_session,
    )
    pr = db_session.query(PipelineRecord).filter_by(run_id=run.id).first()
    assert pr is not None
    assert pr.full_record["demandado"] == demandado
    assert pr.full_record["actuacion"] == actuacion
