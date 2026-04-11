"""End-to-end pipeline tests with mocked HTTP and real PostgreSQL.

Marker: qa_e2e
Requires: PostgreSQL (via test_engine fixture from tests/conftest.py)
"""
from __future__ import annotations

import datetime as dt_module
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = PROJECT_ROOT / "scripts"
for _p in (str(PROJECT_ROOT), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import run_search


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FixedDatetime(dt_module.datetime):
    """datetime subclass that always returns the same 'now'."""

    _fixed = dt_module.datetime(2026, 4, 11, 12, 0, 0, tzinfo=dt_module.timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls._fixed


def _count_runs(engine, label: str) -> int:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) FROM runs WHERE run_label = :lbl"), {"lbl": label}
        ).fetchone()
    return row[0] if row else 0


def _count_pipeline_records(engine, run_label: str) -> int:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT COUNT(*) FROM pipeline_records pr "
                "JOIN runs r ON r.id = pr.run_id "
                "WHERE r.run_label = :lbl"
            ),
            {"lbl": run_label},
        ).fetchone()
    return row[0] if row else 0


# Lazy DB imports — avoids RuntimeError at collection time when DATABASE_URL is absent
def _db_models():
    from db.models import PipelineRecord, Run  # noqa: F401
    return PipelineRecord, Run


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.qa_e2e
def test_e2e_with_db_enrichment_and_persistence(
    mock_portal_and_pdf, patch_session_local, test_engine, qa_db_cleanup, tmp_path
):
    """Pipeline completo con BD: Run existe en DB, PipelineRecords creados, exports en disco."""
    monkeypatch_obj = None  # accessed via mock_portal_and_pdf fixture side-effects

    result = run_search.run_pipeline(
        fecha_inicio="2026-04-11",
        fecha_fin="2026-04-11",
        despacho_ids=None,
        output_root=tmp_path,
        no_db=False,
        draft_emails=False,
        sheets_report=False,
    )

    run_label = result["run_label"]

    # Run should be persisted
    assert _count_runs(test_engine, run_label) == 1, "Run not found in DB"

    # PipelineRecords should be created (2 mock rows)
    assert _count_pipeline_records(test_engine, run_label) == 2, "Expected 2 pipeline records"

    # exports must exist on disk
    exports = result["exports"]
    assert Path(exports["summary_json"]).exists()
    assert Path(exports["records_detailed_json"]).exists()

    # enrichment_enabled must be True
    assert result["metadata"]["enrichment_enabled"] is True


@pytest.mark.qa_e2e
def test_e2e_no_db_flag(mock_portal_and_pdf, tmp_path):
    """With --no-db: BD no es tocada, exports creados, records sin match_camara key."""
    result = run_search.run_pipeline(
        fecha_inicio="2026-04-11",
        fecha_fin="2026-04-11",
        despacho_ids=None,
        output_root=tmp_path,
        no_db=True,
        draft_emails=False,
        sheets_report=False,
    )

    # exports must still be created
    exports = result["exports"]
    assert Path(exports["summary_json"]).exists()
    assert Path(exports["records_detailed_json"]).exists()

    # enrichment_enabled must be False
    assert result["metadata"]["enrichment_enabled"] is False

    # records in run_payload should not have match_camara (enrichment skipped)
    run_payload_path = Path(result["run_dir"]) / "run_payload.json"
    assert run_payload_path.exists()
    import json

    payload = json.loads(run_payload_path.read_text(encoding="utf-8"))
    for record in payload.get("records", []):
        assert "match_camara" not in record, "match_camara should not be set when no_db=True"


@pytest.mark.qa_e2e
def test_e2e_db_connection_failure_mid_run(mock_portal_and_pdf, monkeypatch, tmp_path):
    """get_session raises OperationalError: pipeline NO crashea, exports creados sin enrichment."""
    from sqlalchemy.exc import OperationalError

    import db

    @contextmanager
    def _failing_get_session():
        raise OperationalError("mock connection failure", {}, Exception("refused"))
        yield  # pragma: no cover

    monkeypatch.setattr(db, "get_session", _failing_get_session)

    # Pipeline must not raise
    result = run_search.run_pipeline(
        fecha_inicio="2026-04-11",
        fecha_fin="2026-04-11",
        despacho_ids=None,
        output_root=tmp_path,
        no_db=False,
        draft_emails=False,
        sheets_report=False,
    )

    # exports still created
    assert Path(result["exports"]["summary_json"]).exists()

    # enrichment disabled because DB failed
    assert result["metadata"]["enrichment_enabled"] is False


@pytest.mark.qa_e2e
def test_e2e_db_timeout_during_enrichment(mock_portal_and_pdf, monkeypatch, tmp_path):
    """enrich_records_from_db raises: pipeline completa, enrichment_enabled=False."""
    from sqlalchemy.exc import OperationalError

    def _raising_enrichment(records, session):
        raise OperationalError("statement timeout", {}, Exception("timeout"))

    monkeypatch.setattr(run_search, "enrich_records_from_db", _raising_enrichment)

    result = run_search.run_pipeline(
        fecha_inicio="2026-04-11",
        fecha_fin="2026-04-11",
        despacho_ids=None,
        output_root=tmp_path,
        no_db=False,
        draft_emails=False,
        sheets_report=False,
    )

    assert Path(result["exports"]["summary_json"]).exists()
    assert result["metadata"]["enrichment_enabled"] is False


@pytest.mark.qa_e2e
def test_e2e_rerun_same_label_idempotent(
    mock_portal_and_pdf, patch_session_local, test_engine, monkeypatch, qa_db_cleanup, tmp_path
):
    """Mismo run_label 2 veces: solo 1 Run en DB, sin error."""
    # Fix datetime so both calls generate the same run_label
    monkeypatch.setattr(run_search, "datetime", _FixedDatetime)

    common_kwargs = dict(
        fecha_inicio="2026-04-11",
        fecha_fin="2026-04-11",
        despacho_ids=None,
        output_root=tmp_path,
        no_db=False,
        draft_emails=False,
        sheets_report=False,
    )

    result1 = run_search.run_pipeline(**common_kwargs)
    result2 = run_search.run_pipeline(**common_kwargs)

    # Both calls should succeed
    assert result1["run_label"] == result2["run_label"]

    # Exactly 1 Run in DB (idempotent — second call skips insert)
    label = result1["run_label"]
    assert _count_runs(test_engine, label) == 1, "Expected exactly 1 Run row after 2 identical runs"
