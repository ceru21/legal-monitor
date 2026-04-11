"""Unit tests for split_emails — no DB required."""
import pytest

from enrich_contacts import split_emails


@pytest.mark.unit
class TestSplitEmails:
    def test_single_email(self):
        assert split_emails("user@example.com") == ["user@example.com"]

    def test_semicolon_separator(self):
        result = split_emails("a@a.com;b@b.com")
        assert result == ["a@a.com", "b@b.com"]

    def test_comma_separator(self):
        result = split_emails("a@a.com,b@b.com")
        assert result == ["a@a.com", "b@b.com"]

    def test_space_separator(self):
        result = split_emails("a@a.com b@b.com")
        assert result == ["a@a.com", "b@b.com"]

    def test_duplicates_removed(self):
        result = split_emails("a@a.com;a@a.com;b@b.com")
        assert result == ["a@a.com", "b@b.com"]

    def test_none_returns_empty(self):
        assert split_emails(None) == []

    def test_empty_string_returns_empty(self):
        assert split_emails("") == []

    def test_mixed_delimiters(self):
        result = split_emails("a@a.com; b@b.com,c@c.com")
        assert set(result) == {"a@a.com", "b@b.com", "c@c.com"}

    def test_junk_without_at_filtered(self):
        # Tokens without @ should be excluded
        result = split_emails("notanemail a@b.com")
        assert "notanemail" not in result
        assert "a@b.com" in result

    def test_mixed_valid_and_invalid(self):
        result = split_emails("good@email.com;bad-token;another@email.com")
        assert "good@email.com" in result
        assert "another@email.com" in result
        assert "bad-token" not in result

    def test_email_with_plus_tag(self):
        result = split_emails("user+tag@sub.domain.co")
        assert result == ["user+tag@sub.domain.co"]
