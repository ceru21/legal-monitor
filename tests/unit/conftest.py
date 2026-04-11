"""Unit-level conftest — stubs out db modules so tests run without DATABASE_URL."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Pre-register db stubs before any test imports them.
# patch("db.repository.query_contacts_by_name") would otherwise trigger
# db/__init__.py which raises RuntimeError when DATABASE_URL is not set.
#
# IMPORTANT: patch() resolves "db.repository" via getattr(sys.modules["db"], "repository"),
# while `from db.repository import X` uses sys.modules["db.repository"] directly.
# Both must point to the same object for patching to work correctly.
_db_stub = MagicMock()
_db_models_stub = MagicMock()
_db_repository_stub = MagicMock()

# Wire up the attribute so both resolution paths return the same object
_db_stub.repository = _db_repository_stub
_db_stub.models = _db_models_stub

sys.modules.setdefault("db", _db_stub)
sys.modules.setdefault("db.repository", _db_repository_stub)
sys.modules.setdefault("db.models", _db_models_stub)
