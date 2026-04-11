"""Shared fixtures for the legal-monitor QA suite."""
from __future__ import annotations

import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Make project root importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Test database setup
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://legal_monitor:legal_monitor@localhost:5432/legal_monitor_test",
)

# Base URL without database name to create the test DB
_BASE_URL = TEST_DATABASE_URL.rsplit("/", 1)[0]
_TEST_DB_NAME = TEST_DATABASE_URL.rsplit("/", 1)[1]

# Validate DB name before using it in DDL interpolation
if not re.match(r'^[A-Za-z0-9_]{1,63}$', _TEST_DB_NAME):
    raise ValueError(f"Unsafe test database name: {_TEST_DB_NAME!r}")


@pytest.fixture(scope="session")
def test_engine():
    """Create the test database and all tables; drop on session end."""
    # Connect to postgres to create/drop the test database
    admin_engine = create_engine(f"{_BASE_URL}/postgres", isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}"'))
        conn.execute(text(f'CREATE DATABASE "{_TEST_DB_NAME}"'))
    admin_engine.dispose()

    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)

    # Import models to register them
    from db import Base  # noqa: F401
    import db.models  # noqa: F401

    Base.metadata.create_all(engine)
    yield engine

    engine.dispose()
    admin_engine2 = create_engine(f"{_BASE_URL}/postgres", isolation_level="AUTOCOMMIT")
    with admin_engine2.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}"'))
    admin_engine2.dispose()


@pytest.fixture
def db_session(test_engine):
    """Transactional session — rolls back after each test (fast, isolated)."""
    connection = test_engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = TestSession()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def committed_session(test_engine):
    """Session that commits — use for import_contacts which manages its own session.
    Cleans up all inserted data after the test."""
    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    session = TestSession()
    yield session
    session.close()
    # Cleanup all tables after test
    with test_engine.connect() as conn:
        conn.execute(text("DELETE FROM pipeline_records"))
        conn.execute(text("DELETE FROM runs"))
        conn.execute(text("DELETE FROM contacts"))
        conn.commit()


@pytest.fixture
def patch_session_local(test_engine, monkeypatch):
    """Monkeypatch db.SessionLocal and db.get_session to use the test engine."""
    import db
    TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(db, "SessionLocal", TestSession)

    @contextmanager
    def _test_get_session():
        session = TestSession()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(db, "get_session", _test_get_session)

    # Also patch in import_contacts module if already imported
    try:
        import db.import_contacts as ic
        monkeypatch.setattr(ic, "SessionLocal", TestSession)
    except Exception:
        pass
    return TestSession


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_contact_rows():
    """Raw dicts simulating rows from a Cámara de Comercio TXT file."""
    return [
        {
            "razon_social": "ACME S.A.S.",
            "correo_comercial": "contacto@acme.com",
            "ciudad": "Medellin",
            "nit": "900111222-1",
        },
        {
            "razon_social": "GLOBAL TRADE LTDA",
            "correo_comercial": "info@globaltrade.com",
            "ciudad": "Bogota",
            "nit": "800333444-5",
        },
        {
            "razon_social": "TECNOLOGIAS DEL FUTURO S.A.",
            "correo_comercial": "ventas@tecfuturo.co",
            "ciudad": "Cali",
            "nit": "700555666-0",
        },
        {
            "razon_social": "INVERSIONES ABC",
            "correo_comercial": None,
            "ciudad": "Barranquilla",
            "nit": "600777888-3",
        },
        {
            "razon_social": "DISTRIBUIDORA XYZ S A",
            "correo_comercial": "ventas@xyz.com",
            "ciudad": "Medellin",
            "nit": "500999000-7",
        },
    ]


@pytest.fixture
def sample_pipeline_records():
    """Records as produced by the matcher (pre-enrichment)."""
    return [
        {
            "despacho_id": "DESP001",
            "demandado": "ACME S.A.S.",
            "demandante": "Juan Garcia",
            "decision": "accepted",
            "match_reason": "process_type",
            "tipo_proceso": "ejecutivo",
            "actuacion": "mandamiento de pago",
            "radicado_normalizado": "2024-001",
        },
        {
            "despacho_id": "DESP001",
            "demandado": "EMPRESA INEXISTENTE LTDA",
            "demandante": "Maria Lopez",
            "decision": "review",
            "match_reason": "actuacion",
            "tipo_proceso": "ordinario",
            "actuacion": "notificacion",
            "radicado_normalizado": "2024-002",
        },
        {
            "despacho_id": "DESP002",
            "demandado": None,
            "demandante": "Pedro Ramirez",
            "decision": "accepted",
            "match_reason": "process_type",
            "tipo_proceso": "ejecutivo",
            "actuacion": "embargo",
            "radicado_normalizado": "2024-003",
        },
    ]


@pytest.fixture
def sample_contacts_file(tmp_path):
    """Create a temporary comma-separated TXT file (latin-1) with 5 data rows."""
    content = (
        "razon_social,correo_comercial,ciudad,nit\r\n"
        "ACME S.A.S.,contacto@acme.com,Medellin,900111222-1\r\n"
        "GLOBAL TRADE LTDA,info@globaltrade.com,Bogota,800333444-5\r\n"
        "TECNOLOGIAS DEL FUTURO S.A.,ventas@tecfuturo.co,Cali,700555666-0\r\n"
        "INVERSIONES ABC,,Barranquilla,600777888-3\r\n"
        "DISTRIBUIDORA XYZ S A,ventas@xyz.com,Medellin,500999000-7\r\n"
    )
    f = tmp_path / "sample_contacts.txt"
    f.write_bytes(content.encode("latin-1"))
    return f
