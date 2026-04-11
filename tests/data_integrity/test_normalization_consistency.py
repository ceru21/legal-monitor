"""Data integrity: normalization used at import time == normalization used at query time."""
from __future__ import annotations

import pytest
from db.models import Contact
from db.repository import query_contacts_by_name
from enrich_contacts import normalize_company_name


@pytest.mark.integration
class TestNormalizationConsistency:
    def test_import_and_query_normalize_identically(self, db_session):
        """'ACME S.A.S.' imported → query with 'Acme SAS' must match."""
        razon_social = "ACME S.A.S."
        normalized_import = normalize_company_name(razon_social)

        db_session.add(Contact(
            razon_social=razon_social,
            razon_social_normalizada=normalized_import,
            correo_comercial="a@acme.com",
            source_label="test",
        ))
        db_session.flush()

        # Query using a different casing/format
        query_key = normalize_company_name("Acme SAS")
        result = query_contacts_by_name(query_key, db_session)
        assert "a@acme.com" in result, (
            f"Normalization mismatch: import='{normalized_import}', query='{query_key}'"
        )

    def test_normalize_is_idempotent(self):
        names = [
            "EMPRESA GRANDE S.A.S.",
            "GLOBAL TRADE LTDA",
            "  ESPACIOS   MULTIPLES  ",
            "EMPRESA & CIA. S.A.",
        ]
        for name in names:
            first = normalize_company_name(name)
            second = normalize_company_name(first)
            assert first == second, f"Not idempotent for '{name}': first='{first}', second='{second}'"

    def test_suffix_variants_produce_same_key(self):
        variants = ["ACME SAS", "ACME S.A.S.", "ACME S A S", "ACME SOCIEDAD POR ACCIONES SIMPLIFICADA"]
        keys = [normalize_company_name(v) for v in variants]
        # All variants of SAS should normalize to same base
        assert len(set(keys)) == 1, f"Expected all same, got: {keys}"
