"""Unit tests for normalize_company_name — no DB required."""
import pytest

pytest.importorskip("scripts")

from enrich_contacts import normalize_company_name


@pytest.mark.unit
class TestNormalizeCompanyName:
    def test_removes_sas_suffix(self):
        assert normalize_company_name("ACME S.A.S.") == "acme"

    def test_removes_ltda_suffix(self):
        assert normalize_company_name("GLOBAL TRADE LTDA") == "global trade"

    def test_removes_sa_suffix(self):
        assert normalize_company_name("TECNOLOGIAS DEL FUTURO S.A.") == "tecnologias del futuro"

    def test_removes_sa_without_dots(self):
        assert normalize_company_name("DISTRIBUIDORA XYZ S A") == "distribuidora xyz"

    def test_none_returns_empty(self):
        assert normalize_company_name(None) == ""

    def test_empty_string_returns_empty(self):
        assert normalize_company_name("") == ""

    def test_accented_chars_normalized(self):
        # Acentos deben convertirse a ASCII
        result = normalize_company_name("COMPAÑIA AÉREA S.A.")
        assert "compania" in result or "compaa" in result  # NFKD strips ñ→n + combining
        # Key: no crash, returns string
        assert isinstance(result, str)

    def test_multiple_spaces_collapsed(self):
        assert normalize_company_name("EMPRESA   GRANDE   LTDA") == "empresa grande"

    def test_special_chars_replaced(self):
        result = normalize_company_name("EMPRESA & CIA. S.A.")
        assert "&" not in result
        assert "." not in result

    def test_suffix_in_middle_not_removed(self):
        # "sas" in the middle should NOT be removed, only at end
        result = normalize_company_name("SAS DISTRIBUCIONES")
        assert result == "sas distribuciones"

    def test_name_is_only_suffix_not_removed_without_space(self):
        # CORP_SUFFIXES patterns require a preceding space (e.g. " ltda").
        # "LTDA" alone does NOT match " ltda" so it remains "ltda", not "".
        result = normalize_company_name("LTDA")
        assert result == "ltda"  # suffix removal requires leading space

    def test_idempotent(self):
        name = "EMPRESA EJEMPLO S.A.S."
        first = normalize_company_name(name)
        second = normalize_company_name(first)
        assert first == second
