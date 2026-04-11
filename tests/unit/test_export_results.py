"""Unit tests for export_results — no DB required."""
from __future__ import annotations

import pytest

from export_results import (
    OPERATIVE_COLUMNS,
    _select_columns,
    build_export_payload,
)


@pytest.mark.unit
class TestSelectColumns:
    def test_returns_only_requested_columns(self):
        record = {"a": 1, "b": 2, "c": 3}
        result = _select_columns(record, ["a", "c"])
        assert result == {"a": 1, "c": 3}

    def test_missing_columns_return_none(self):
        record = {"a": 1}
        result = _select_columns(record, ["a", "missing"])
        assert result["missing"] is None

    def test_empty_record(self):
        result = _select_columns({}, ["col1", "col2"])
        assert result == {"col1": None, "col2": None}


@pytest.mark.unit
class TestBuildExportPayload:
    def _make_records(self):
        return [
            {
                "decision": "accepted",
                "demandado": "ACME",
                "pdf_path": "/path/to/pdf1.pdf",
                "despacho_id": "DESP001",
                "revision_manual": "si",
                "match_camara": True,
                "emails_encontrados": ["a@b.com"],
            },
            {
                "decision": "review",
                "demandado": "EMPRESA",
                "pdf_path": "/path/to/pdf1.pdf",
                "despacho_id": "DESP001",
                "revision_manual": "no",
                "match_camara": False,
                "emails_encontrados": [],
            },
            {
                "decision": "rejected",
                "demandado": "OTRO",
                "pdf_path": "/path/to/pdf2.pdf",
                "despacho_id": "DESP002",
                "revision_manual": "no",
            },
        ]

    def test_operative_rows_only_accepted_and_review(self):
        records = self._make_records()
        payload = build_export_payload("test_run", {}, records)
        decisions = {r["decision"] for r in payload["operative_records"]}
        assert "rejected" not in decisions
        assert "accepted" in decisions
        assert "review" in decisions

    def test_summary_counts_correct(self):
        records = self._make_records()
        payload = build_export_payload("test_run", {}, records)
        summary = payload["summary"]
        assert summary["accepted"] == 1
        assert summary["review"] == 1
        assert summary["rejected"] == 1
        assert summary["rows_total"] == 3

    def test_pdf_summaries_grouped_by_pdf(self):
        records = self._make_records()
        payload = build_export_payload("test_run", {}, records)
        # 2 distinct pdf_paths
        assert len(payload["pdf_summaries"]) == 2

    def test_manual_review_count(self):
        records = self._make_records()
        payload = build_export_payload("test_run", {}, records)
        assert payload["summary"]["manual_review_yes"] == 1

    def test_emails_encontrados_as_list_in_operative(self):
        # JSON payload keeps emails as list (correct for JSON consumers).
        # CSV serialization is handled by write_csv (fixed in utils.py).
        records = self._make_records()
        payload = build_export_payload("test_run", {}, records)
        operative = [r for r in payload["operative_records"] if r.get("emails_encontrados")]
        if operative:
            emails = operative[0]["emails_encontrados"]
            assert isinstance(emails, list)


@pytest.mark.unit
class TestOperativeColumns:
    def test_match_camara_in_operative_columns(self):
        assert "match_camara" in OPERATIVE_COLUMNS

    def test_emails_encontrados_in_operative_columns(self):
        assert "emails_encontrados" in OPERATIVE_COLUMNS

    def test_legacy_2023_columns_not_in_operative(self):
        assert "match_2023" not in OPERATIVE_COLUMNS
        assert "email_2023" not in OPERATIVE_COLUMNS

    def test_legacy_2025_columns_not_in_operative(self):
        assert "match_2025" not in OPERATIVE_COLUMNS
        assert "email_2025" not in OPERATIVE_COLUMNS
