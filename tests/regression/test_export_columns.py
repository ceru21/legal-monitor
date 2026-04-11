"""Regression: operative column list has new fields and not legacy fields."""
import pytest
from export_results import OPERATIVE_COLUMNS, build_export_payload


@pytest.mark.unit
class TestExportColumns:
    def test_match_camara_present(self):
        assert "match_camara" in OPERATIVE_COLUMNS

    def test_emails_encontrados_present(self):
        assert "emails_encontrados" in OPERATIVE_COLUMNS

    def test_match_2023_absent(self):
        assert "match_2023" not in OPERATIVE_COLUMNS

    def test_match_2025_absent(self):
        assert "match_2025" not in OPERATIVE_COLUMNS

    def test_email_2023_absent(self):
        assert "email_2023" not in OPERATIVE_COLUMNS

    def test_email_2025_absent(self):
        assert "email_2025" not in OPERATIVE_COLUMNS

    def test_operative_rows_have_new_fields(self):
        records = [
            {
                "decision": "accepted",
                "match_camara": True,
                "emails_encontrados": ["a@b.com"],
                "demandado": "ACME",
                "despacho_id": "D001",
            }
        ]
        payload = build_export_payload("test", {}, records)
        operative = payload["operative_records"]
        assert len(operative) == 1
        assert operative[0]["match_camara"] is True
        assert operative[0]["emails_encontrados"] == ["a@b.com"]
