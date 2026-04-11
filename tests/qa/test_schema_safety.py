"""Schema DDL safety and constraint tests.

Marker: qa_schema
Requires: PostgreSQL (via test_engine fixture from tests/conftest.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(PROJECT_ROOT), str(PROJECT_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# DB imports are lazy (inside tests) to allow collection without DATABASE_URL


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.qa_schema
def test_create_all_idempotent_no_data_loss(test_engine, qa_db_cleanup):
    """create_all() después de insertar datos no pierde filas."""
    from db import Base
    from db.models import Contact

    Session = sessionmaker(bind=test_engine)
    session = Session()
    try:
        session.add(
            Contact(
                razon_social="ACME S.A.S.",
                razon_social_normalizada="acme",
                correo_comercial="contacto@acme.com",
                source_label="schema_test",
            )
        )
        session.commit()
    finally:
        session.close()

    # Run create_all again — must be a no-op (checkfirst=True by default)
    Base.metadata.create_all(test_engine)

    with test_engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) FROM contacts WHERE source_label = 'schema_test'")
        ).fetchone()
    assert row[0] >= 1, "Data was lost after create_all()"


@pytest.mark.qa_schema
def test_column_types_match_repository(test_engine):
    """Inspector: runs.metadata es JSONB, pipeline_records.emails_encontrados es ARRAY."""
    from db import Base  # noqa: F401 — ensures models are registered
    import db.models  # noqa: F401

    inspector = inspect(test_engine)

    # Check runs.metadata column
    run_cols = {c["name"]: c for c in inspector.get_columns("runs")}
    assert "metadata" in run_cols, "runs.metadata column not found"
    # The type should be JSONB (or its string representation)
    metadata_type = str(run_cols["metadata"]["type"]).upper()
    assert "JSON" in metadata_type, f"runs.metadata type is not JSON-based: {metadata_type}"

    # Check pipeline_records.emails_encontrados
    pr_cols = {c["name"]: c for c in inspector.get_columns("pipeline_records")}
    assert "emails_encontrados" in pr_cols, "pipeline_records.emails_encontrados not found"
    emails_type = str(pr_cols["emails_encontrados"]["type"]).upper()
    assert "ARRAY" in emails_type or "TEXT" in emails_type, (
        f"pipeline_records.emails_encontrados unexpected type: {emails_type}"
    )

    # Check pipeline_records.full_record
    assert "full_record" in pr_cols, "pipeline_records.full_record not found"
    full_record_type = str(pr_cols["full_record"]["type"]).upper()
    assert "JSON" in full_record_type, f"full_record type is not JSON-based: {full_record_type}"


@pytest.mark.qa_schema
def test_unique_constraint_run_label(test_engine, qa_db_cleanup):
    """INSERT duplicado directo (sin ORM idempotency): IntegrityError."""
    label = "schema-unique-test"

    with test_engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO runs (run_label, fecha_inicio, fecha_fin) "
                "VALUES (:lbl, '2026-04-11', '2026-04-11')"
            ),
            {"lbl": label},
        )
        conn.commit()

    with pytest.raises(IntegrityError):
        with test_engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO runs (run_label, fecha_inicio, fecha_fin) "
                    "VALUES (:lbl, '2026-04-11', '2026-04-11')"
                ),
                {"lbl": label},
            )
            conn.commit()


@pytest.mark.qa_schema
def test_fk_constraint_pipeline_records(test_engine):
    """PipelineRecord con run_id inexistente: IntegrityError."""
    with pytest.raises(IntegrityError):
        with test_engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO pipeline_records (run_id, decision) "
                    "VALUES (999999999, 'accepted')"
                )
            )
            conn.commit()


@pytest.mark.qa_schema
def test_cascade_delete_at_db_level(test_engine, qa_db_cleanup):
    """DELETE Run → PipelineRecords eliminados automáticamente por CASCADE."""
    label = "schema-cascade-test"

    with test_engine.connect() as conn:
        result = conn.execute(
            text(
                "INSERT INTO runs (run_label, fecha_inicio, fecha_fin) "
                "VALUES (:lbl, '2026-04-11', '2026-04-11') RETURNING id"
            ),
            {"lbl": label},
        )
        run_id = result.fetchone()[0]
        conn.execute(
            text(
                "INSERT INTO pipeline_records (run_id, decision) VALUES (:rid, 'accepted')"
            ),
            {"rid": run_id},
        )
        conn.commit()

    # Verify record exists
    with test_engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) FROM pipeline_records WHERE run_id = :rid"),
            {"rid": run_id},
        ).fetchone()
    assert row[0] == 1

    # Delete the run
    with test_engine.connect() as conn:
        conn.execute(text("DELETE FROM runs WHERE id = :rid"), {"rid": run_id})
        conn.commit()

    # Cascade should have deleted the pipeline_records
    with test_engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) FROM pipeline_records WHERE run_id = :rid"),
            {"rid": run_id},
        ).fetchone()
    assert row[0] == 0, "CASCADE DELETE did not remove pipeline_records"
