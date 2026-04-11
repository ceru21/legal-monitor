"""Regression: legacy file-based enrichment still works."""
from __future__ import annotations

from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.unit
class TestLegacyEnrich:
    def test_load_contact_index_reads_file(self):
        from enrich_contacts import load_contact_index
        index = load_contact_index(FIXTURES / "sample_contacts.txt")
        assert isinstance(index, dict)
        assert len(index) > 0

    def test_load_contact_index_has_normalized_keys(self):
        from enrich_contacts import load_contact_index
        index = load_contact_index(FIXTURES / "sample_contacts.txt")
        # ACME S.A.S. → "acme"
        assert "acme" in index

    def test_load_contact_index_has_emails(self):
        from enrich_contacts import load_contact_index
        index = load_contact_index(FIXTURES / "sample_contacts.txt")
        assert "contacto@acme.com" in index["acme"]["emails"]

    def test_enrich_record_legacy_with_2023_2025_indexes(self):
        from enrich_contacts import enrich_record, load_contact_index
        idx = load_contact_index(FIXTURES / "sample_contacts.txt")
        record = {"demandado": "ACME S.A.S.", "decision": "accepted"}
        enriched = enrich_record(record, idx2023=idx, idx2025={})
        assert enriched["match_2023"] is True
        assert "contacto@acme.com" in enriched["email_2023"]
        assert enriched["match_2025"] is False

    def test_enrich_records_legacy_end_to_end(self):
        from enrich_contacts import enrich_records
        records = [
            {"demandado": "ACME S.A.S.", "decision": "accepted"},
            {"demandado": "EMPRESA INEXISTENTE", "decision": "review"},
        ]
        enriched = enrich_records(
            records,
            file_2023=FIXTURES / "sample_contacts.txt",
            file_2025=FIXTURES / "sample_contacts.txt",
        )
        assert len(enriched) == 2
        assert enriched[0]["match_total"] is True
        assert enriched[1]["match_total"] is False

    def test_load_unicode_file(self):
        from enrich_contacts import load_contact_index
        index = load_contact_index(FIXTURES / "sample_contacts_unicode.txt")
        assert isinstance(index, dict)
        # Should not crash on latin-1 accented characters
