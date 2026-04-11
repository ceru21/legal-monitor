"""Unit tests for enrich_record_from_db — uses mocks, no real DB."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from enrich_contacts import enrich_record_from_db


def _mock_session():
    return MagicMock()


@pytest.mark.unit
class TestEnrichRecordFromDb:
    def test_match_with_emails(self):
        record = {"demandado": "ACME S.A.S.", "decision": "accepted"}
        with patch("enrich_contacts.enrich_record_from_db.__wrapped__" if hasattr(enrich_record_from_db, "__wrapped__") else "db.repository.query_contacts_by_name") as _:
            pass
        # Direct patch of the import inside the function
        with patch("db.repository.query_contacts_by_name", return_value=["contacto@acme.com"]):
            result = enrich_record_from_db(record, _mock_session())
        assert result["match_camara"] is True
        assert "contacto@acme.com" in result["emails_encontrados"]

    def test_no_match_returns_false(self):
        record = {"demandado": "EMPRESA INEXISTENTE LTDA", "decision": "review"}
        with patch("db.repository.query_contacts_by_name", return_value=[]):
            result = enrich_record_from_db(record, _mock_session())
        assert result["match_camara"] is False
        assert result["emails_encontrados"] == []

    def test_demandado_none_returns_false(self):
        record = {"demandado": None, "decision": "accepted"}
        with patch("db.repository.query_contacts_by_name", return_value=[]):
            result = enrich_record_from_db(record, _mock_session())
        assert result["match_camara"] is False
        assert result["emails_encontrados"] == []

    def test_duplicate_emails_deduplicated(self):
        # Two contacts with same email
        record = {"demandado": "ACME S.A.S.", "decision": "accepted"}
        with patch("db.repository.query_contacts_by_name", return_value=["a@a.com", "a@a.com", "b@b.com"]):
            result = enrich_record_from_db(record, _mock_session())
        assert result["emails_encontrados"].count("a@a.com") == 1

    def test_original_fields_preserved(self):
        record = {"demandado": "ACME S.A.S.", "decision": "accepted", "radicado_normalizado": "2024-001"}
        with patch("db.repository.query_contacts_by_name", return_value=["a@b.com"]):
            result = enrich_record_from_db(record, _mock_session())
        assert result["decision"] == "accepted"
        assert result["radicado_normalizado"] == "2024-001"
        assert "demandado_normalizado_match" in result
