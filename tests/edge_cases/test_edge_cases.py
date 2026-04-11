"""Edge case tests for various pipeline components."""
from __future__ import annotations

from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.unit
class TestEdgeCases:
    def test_empty_file_import_returns_zero(self):
        from enrich_contacts import load_contact_index
        index = load_contact_index(FIXTURES / "sample_contacts_empty.txt")
        assert index == {}

    def test_razon_social_normalizes_to_empty_skipped_in_index(self):
        """A company whose name is only a suffix normalizes to '' and is skipped."""
        from enrich_contacts import load_contact_index
        import tempfile, os
        content = "razon_social\tcorreo_comercial\r\nLTDA\ta@b.com\r\n"
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".txt", delete=False) as f:
            f.write(content.encode("latin-1"))
            fname = f.name
        try:
            index = load_contact_index(fname)
            assert "" not in index, "Empty string key should be skipped"
        finally:
            os.unlink(fname)

    def test_demandado_none_enrich_returns_false(self):
        from unittest.mock import patch
        from enrich_contacts import enrich_record_from_db
        from unittest.mock import MagicMock
        record = {"demandado": None}
        with patch("db.repository.query_contacts_by_name", return_value=[]):
            result = enrich_record_from_db(record, MagicMock())
        assert result["match_camara"] is False
        assert result["emails_encontrados"] == []

    def test_very_long_company_name_no_crash(self):
        from enrich_contacts import normalize_company_name
        long_name = "A" * 1000 + " S.A.S."
        result = normalize_company_name(long_name)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_email_with_plus_tag_preserved(self):
        from enrich_contacts import split_emails
        result = split_emails("user+tag@sub.domain.co")
        assert result == ["user+tag@sub.domain.co"]

    def test_record_all_none_fields_no_crash(self):
        from export_results import build_export_payload
        records = [{"decision": "accepted", **{k: None for k in [
            "demandado", "demandante", "despacho_id", "match_camara", "emails_encontrados"
        ]}}]
        payload = build_export_payload("test", {}, records)
        assert len(payload["operative_records"]) == 1


@pytest.mark.integration
class TestEdgeCasesDB:
    def test_record_all_none_save_run_ok(self, db_session):
        from db.repository import save_run
        record = {
            "despacho_id": None,
            "demandado": None,
            "decision": None,
            "match_camara": None,
            "emails_encontrados": None,
        }
        run = save_run(
            run_label="test_all_none",
            fecha_inicio="2024-01-01",
            fecha_fin="2024-01-31",
            metadata={},
            records=[record],
            session=db_session,
        )
        assert run.id is not None
