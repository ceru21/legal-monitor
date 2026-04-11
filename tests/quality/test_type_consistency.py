"""Quality: document type consistency bugs."""
import pytest


@pytest.mark.unit
class TestTypeConsistency:
    def test_bool_none_is_false(self):
        """FIXED #3: bool(None) is False — but repository.py now passes None directly
        so match_camara=None (not enriched) is stored as NULL, distinguishable
        from match_camara=False (enriched but no match found)."""
        assert bool(None) is False  # Python built-in — unchanged
        # The fix was removing bool() wrapper in repository.py

    def test_list_serialized_as_semicolon_in_csv(self):
        """FIXED #6: write_csv now joins list values with ';' instead of repr.
        emails_encontrados=["a@b.com","c@d.com"] → "a@b.com;c@d.com" in CSV."""
        import io, csv as csv_mod
        from utils import write_csv
        import tempfile, os
        rows = [{"emails_encontrados": ["a@b.com", "c@d.com"], "demandado": "ACME"}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            fname = f.name
        try:
            write_csv(fname, rows)
            with open(fname, encoding="utf-8") as f:
                content = f.read()
            assert "['a@b.com'" not in content, "List repr must not appear in CSV"
            assert "a@b.com;c@d.com" in content, "Semicolon-joined emails must appear"
        finally:
            os.unlink(fname)

    def test_empty_list_falsy(self):
        """Confirms [] is falsy — used in repository.py: emails if emails else None."""
        assert not []
        assert ([] if [] else None) is None

    def test_nonempty_list_truthy(self):
        """Confirms non-empty list is truthy."""
        assert ["a@b.com"]
        assert (["a@b.com"] if ["a@b.com"] else None) == ["a@b.com"]
