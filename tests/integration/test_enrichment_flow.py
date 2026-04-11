"""Integration test: full enrichment flow from contacts to enriched records."""
from __future__ import annotations

import pytest
from db.models import Contact
from enrich_contacts import enrich_records_from_db


@pytest.mark.integration
class TestEnrichmentFlow:
    def _insert_contacts(self, session):
        session.add(Contact(
            razon_social="ACME S.A.S.",
            razon_social_normalizada="acme",
            correo_comercial="contacto@acme.com",
            source_label="test",
        ))
        session.add(Contact(
            razon_social="GLOBAL TRADE LTDA",
            razon_social_normalizada="global trade",
            correo_comercial="info@globaltrade.com",
            source_label="test",
        ))
        session.flush()

    def test_match_found_sets_match_camara_true(self, db_session):
        self._insert_contacts(db_session)
        records = [{"demandado": "ACME S.A.S.", "decision": "accepted"}]
        enriched = enrich_records_from_db(records, db_session)
        assert enriched[0]["match_camara"] is True

    def test_match_found_populates_emails(self, db_session):
        self._insert_contacts(db_session)
        records = [{"demandado": "ACME S.A.S.", "decision": "accepted"}]
        enriched = enrich_records_from_db(records, db_session)
        assert "contacto@acme.com" in enriched[0]["emails_encontrados"]

    def test_no_match_sets_match_camara_false(self, db_session):
        self._insert_contacts(db_session)
        records = [{"demandado": "EMPRESA INEXISTENTE LTDA", "decision": "accepted"}]
        enriched = enrich_records_from_db(records, db_session)
        assert enriched[0]["match_camara"] is False
        assert enriched[0]["emails_encontrados"] == []

    def test_multiple_records_enriched(self, db_session):
        self._insert_contacts(db_session)
        records = [
            {"demandado": "ACME S.A.S.", "decision": "accepted"},
            {"demandado": "GLOBAL TRADE LTDA", "decision": "review"},
            {"demandado": "NOBODY INC", "decision": "rejected"},
        ]
        enriched = enrich_records_from_db(records, db_session)
        assert enriched[0]["match_camara"] is True
        assert enriched[1]["match_camara"] is True
        assert enriched[2]["match_camara"] is False

    def test_demandado_none_no_crash(self, db_session):
        self._insert_contacts(db_session)
        records = [{"demandado": None, "decision": "accepted"}]
        enriched = enrich_records_from_db(records, db_session)
        assert enriched[0]["match_camara"] is False

    def test_emails_deduped_across_contacts(self, db_session):
        # Two contacts with same name and same email
        for _ in range(2):
            db_session.add(Contact(
                razon_social="ACME S.A.S.",
                razon_social_normalizada="acme",
                correo_comercial="contacto@acme.com",
                source_label="test",
            ))
        db_session.flush()
        records = [{"demandado": "ACME S.A.S.", "decision": "accepted"}]
        enriched = enrich_records_from_db(records, db_session)
        # query_contacts_by_name returns all rows, split_emails deduplicates
        assert enriched[0]["emails_encontrados"].count("contacto@acme.com") == 1
