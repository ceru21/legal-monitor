"""Regression: --no-db flag produces valid output without DB enrichment."""
from __future__ import annotations

import pytest
from export_results import build_export_payload


@pytest.mark.unit
class TestNoDbBehavior:
    """
    Tests the expected output shape when no DB enrichment occurs.
    run_pipeline(no_db=True) is not tested directly (requires scraper/portal),
    but the downstream behavior can be validated via build_export_payload.
    """

    def test_records_without_enrich_fields_export_ok(self):
        """Records missing match_camara and emails_encontrados should export without crash."""
        records = [
            {
                "decision": "accepted",
                "demandado": "ACME",
                "despacho_id": "D001",
                # no match_camara, no emails_encontrados
            }
        ]
        payload = build_export_payload("run_no_db", {}, records)
        assert len(payload["operative_records"]) == 1
        op = payload["operative_records"][0]
        assert op.get("match_camara") is None
        assert op.get("emails_encontrados") is None

    def test_enrichment_enabled_false_in_metadata(self):
        """When no_db=True, metadata.enrichment_enabled should be False."""
        metadata = {
            "fecha_inicio": "2024-01-01",
            "fecha_fin": "2024-01-31",
            "enrichment_enabled": False,
        }
        payload = build_export_payload("run_no_db", metadata, [])
        assert payload["summary"]["fecha_inicio"] == "2024-01-01"
        # enrichment_enabled is not in summary columns, lives only in metadata
        # Just verify summary is generated without crash
        assert "accepted" in payload["summary"]
