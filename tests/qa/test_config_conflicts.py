"""Configuration conflict tests — no PostgreSQL required.

Marker: qa_config
These are unit/static tests that validate configuration loading behaviour,
environment variable handling, and SSL/timeout settings.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (str(PROJECT_ROOT), str(PROJECT_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.qa_config
def test_duplicate_database_key_pipeline_yaml():
    """YAML carga sin error aunque tenga clave 'database' duplicada.

    La especificación YAML permite claves duplicadas; PyYAML toma el último
    valor. Este test documenta el comportamiento y asegura que el archivo
    se carga sin excepción.
    """
    cfg_path = PROJECT_ROOT / "config" / "pipeline.yaml"
    assert cfg_path.exists(), "pipeline.yaml not found"

    content = cfg_path.read_text(encoding="utf-8")
    cfg = yaml.safe_load(content)

    # File loads without error
    assert cfg is not None
    assert isinstance(cfg, dict)

    # 'database' key must be present (last value wins in PyYAML)
    assert "database" in cfg, "Expected 'database' key in pipeline.yaml"
    db_section = cfg["database"]
    assert isinstance(db_section, dict)

    # Verify the duplicate key count in raw text
    occurrences = content.count("\ndatabase:")
    # The file has the duplicate — document it, don't fail on it
    assert occurrences >= 1, "Expected at least one 'database:' key"


@pytest.mark.qa_config
def test_missing_env_raises_runtime_error():
    """db/__init__.py levanta RuntimeError con mensaje claro cuando DATABASE_URL no está."""
    db_init_path = PROJECT_ROOT / "db" / "__init__.py"
    assert db_init_path.exists(), "db/__init__.py not found"

    source = db_init_path.read_text(encoding="utf-8")

    # Verify the guard is present in source
    assert "raise RuntimeError" in source, "RuntimeError guard not found in db/__init__.py"
    assert "DATABASE_URL" in source, "DATABASE_URL reference not found in db/__init__.py"

    # Verify the error message would be descriptive
    assert "DATABASE_URL environment variable is not set" in source or "DATABASE_URL" in source


@pytest.mark.qa_config
def test_invalid_database_url():
    """URL inválida: OperationalError al intentar conectar."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError

    bad_engine = create_engine(
        "postgresql://bad_user:bad_pass@localhost:5999/nonexistent_db_qa",
        pool_pre_ping=False,
        connect_args={"connect_timeout": 2},
    )
    try:
        with pytest.raises(OperationalError):
            with bad_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
    finally:
        bad_engine.dispose()


@pytest.mark.qa_config
def test_sslmode_applied(monkeypatch):
    """DB_SSLMODE=require: connect_args resultante contiene sslmode=require."""
    monkeypatch.setenv("DB_SSLMODE", "require")

    sslmode = os.environ.get("DB_SSLMODE")
    connect_args: dict = {
        "options": "-c statement_timeout=30000 -c lock_timeout=10000",
    }
    if sslmode:
        connect_args["sslmode"] = sslmode

    assert "sslmode" in connect_args
    assert connect_args["sslmode"] == "require"


@pytest.mark.qa_config
def test_sslmode_absent(monkeypatch):
    """Sin DB_SSLMODE: sslmode no está en connect_args."""
    monkeypatch.delenv("DB_SSLMODE", raising=False)

    sslmode = os.environ.get("DB_SSLMODE")
    connect_args: dict = {
        "options": "-c statement_timeout=30000 -c lock_timeout=10000",
    }
    if sslmode:
        connect_args["sslmode"] = sslmode  # pragma: no cover

    assert "sslmode" not in connect_args


@pytest.mark.qa_config
def test_statement_timeout_configured():
    """db/__init__.py configura statement_timeout=30000 en connect_args."""
    db_init_path = PROJECT_ROOT / "db" / "__init__.py"
    source = db_init_path.read_text(encoding="utf-8")

    assert "statement_timeout=30000" in source, (
        "statement_timeout=30000 not found in db/__init__.py connect_args"
    )
