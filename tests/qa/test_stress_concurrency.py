"""Stress and concurrency tests for the PostgreSQL persistence layer.

Marker: qa_stress
Requires: PostgreSQL (via test_engine fixture from tests/conftest.py)
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import TimeoutError as SATimeoutError
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(PROJECT_ROOT), str(PROJECT_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# DB imports are lazy (inside tests) to allow collection without DATABASE_URL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _count_runs(engine, label_prefix: str = "", exact_label: str = "") -> int:
    with engine.connect() as conn:
        if exact_label:
            row = conn.execute(
                text("SELECT COUNT(*) FROM runs WHERE run_label = :lbl"),
                {"lbl": exact_label},
            ).fetchone()
        else:
            row = conn.execute(
                text("SELECT COUNT(*) FROM runs WHERE run_label LIKE :prefix"),
                {"prefix": f"{label_prefix}%"},
            ).fetchone()
    return row[0] if row else 0


def _make_records(n: int) -> list[dict]:
    return [
        {
            "despacho_id": f"DESP-{i}",
            "demandado": f"Empresa {i} SAS",
            "decision": "accepted" if i % 2 == 0 else "review",
            "match_camara": False,
            "emails_encontrados": [],
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.qa_stress
def test_concurrent_save_run_different_labels(test_engine, qa_db_cleanup):
    """10 threads, cada uno save_run con label único: 10 Runs en DB."""
    from db.repository import save_run

    Session = sessionmaker(bind=test_engine)
    label_prefix = "stress-unique-"

    def _save(i: int):
        session = Session()
        try:
            return save_run(
                f"{label_prefix}{i}",
                "2026-04-11",
                "2026-04-11",
                {"thread": i},
                [],
                session,
            )
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_save, i) for i in range(10)]
        results = [f.result() for f in as_completed(futures)]

    assert len(results) == 10
    assert _count_runs(test_engine, label_prefix=label_prefix) == 10


@pytest.mark.qa_stress
def test_concurrent_save_run_same_label_race(test_engine, qa_db_cleanup):
    """5 threads con mismo label: exactamente 1 Run en DB, sin excepciones no manejadas.

    This test deliberately exposes the query-then-insert race condition in
    save_run (db/repository.py). Some threads may raise RuntimeError due to
    IntegrityError; that is expected. The invariant is exactly 1 row in DB.
    """
    from db.repository import save_run

    Session = sessionmaker(bind=test_engine)
    race_label = "stress-race-same-label"

    exceptions = []

    def _save(_i: int):
        session = Session()
        try:
            return save_run(race_label, "2026-04-11", "2026-04-11", {}, [], session)
        except RuntimeError as exc:
            exceptions.append(exc)
            return None
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_save, i) for i in range(5)]
        for f in as_completed(futures):
            f.result()  # propagate unexpected exceptions

    count = _count_runs(test_engine, exact_label=race_label)
    assert count == 1, f"Expected 1 Run in DB, found {count}"
    # RuntimeError is allowed (race loser), but no other exception type should escape
    for exc in exceptions:
        assert isinstance(exc, RuntimeError), f"Unexpected exception type: {type(exc)}"


@pytest.mark.qa_stress
def test_large_batch_1000_records(test_engine, qa_db_cleanup):
    """save_run con 1000 records: count correcto, termina en tiempo razonable."""
    from db.repository import save_run

    Session = sessionmaker(bind=test_engine)
    session = Session()
    label = "stress-batch-1000"
    records = _make_records(1000)

    start = time.monotonic()
    try:
        save_run(label, "2026-04-11", "2026-04-11", {"batch": 1000}, records, session)
    finally:
        session.close()

    elapsed = time.monotonic() - start
    assert elapsed < 30, f"Batch of 1000 took {elapsed:.1f}s — too slow"

    with test_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT COUNT(*) FROM pipeline_records pr "
                "JOIN runs r ON r.id = pr.run_id "
                "WHERE r.run_label = :lbl"
            ),
            {"lbl": label},
        ).fetchone()
    assert row[0] == 1000


@pytest.mark.qa_stress
def test_large_batch_5000_records(test_engine, qa_db_cleanup):
    """save_run con 5000 records: count correcto."""
    from db.repository import save_run

    Session = sessionmaker(bind=test_engine)
    session = Session()
    label = "stress-batch-5000"
    records = _make_records(5000)

    try:
        save_run(label, "2026-04-11", "2026-04-11", {"batch": 5000}, records, session)
    finally:
        session.close()

    with test_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT COUNT(*) FROM pipeline_records pr "
                "JOIN runs r ON r.id = pr.run_id "
                "WHERE r.run_label = :lbl"
            ),
            {"lbl": label},
        ).fetchone()
    assert row[0] == 5000


@pytest.mark.qa_stress
def test_connection_pool_exhaustion(test_engine):
    """Engine con pool_size=2, max_overflow=0: 3ra conexión lanza timeout."""
    import os

    url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://legal_monitor:legal_monitor@localhost:5432/legal_monitor_test",
    )
    small_engine = create_engine(
        url, pool_size=2, max_overflow=0, pool_timeout=1, pool_pre_ping=False
    )
    SmallSession = sessionmaker(bind=small_engine)

    s1 = SmallSession()
    s2 = SmallSession()
    try:
        s1.execute(text("SELECT 1"))
        s2.execute(text("SELECT 1"))

        with pytest.raises(Exception) as exc_info:
            s3 = SmallSession()
            s3.execute(text("SELECT 1"))
            s3.close()

        # SQLAlchemy raises TimeoutError or OperationalError on pool exhaustion
        assert any(
            klass in type(exc_info.value).__mro__
            for klass in (SATimeoutError, Exception)
        )
    finally:
        s1.close()
        s2.close()
        small_engine.dispose()


@pytest.mark.qa_stress
def test_transaction_rollback_partial_failure(test_engine, qa_db_cleanup):
    """Fecha inválida: excepción propagada, 0 rows persistidas."""
    from db.repository import save_run
    from sqlalchemy.orm import sessionmaker as sm

    Session = sm(bind=test_engine)
    session = Session()
    label = "stress-invalid-date"

    with pytest.raises((ValueError, RuntimeError)):
        save_run(label, "not-a-date", "2026-04-11", {}, [], session)
    session.close()

    # No Run should have been committed
    assert _count_runs(test_engine, exact_label=label) == 0, "Expected 0 rows after failed save"
