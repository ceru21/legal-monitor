"""Edge cases for save_run — documents known bugs."""
from __future__ import annotations

import pytest
from db.models import PipelineRecord
from db.repository import save_run


@pytest.mark.integration
class TestSaveRunEdgeCases:
    def test_match_camara_none_stored_as_null(self, db_session):
        # FIXED #3: match_camara=None now stored as NULL (not converted to False)
        run = save_run(
            run_label="fixed_match_none",
            fecha_inicio="2024-01-01",
            fecha_fin="2024-01-31",
            metadata={},
            records=[{"despacho_id": "D1", "demandado": "X", "decision": "accepted", "match_camara": None, "emails_encontrados": []}],
            session=db_session,
        )
        pr = db_session.query(PipelineRecord).filter(PipelineRecord.run_id == run.id).first()
        assert pr.match_camara is None

    def test_duplicate_run_label_returns_existing(self, db_session):
        run1 = save_run(
            run_label="dup_label",
            fecha_inicio="2024-01-01",
            fecha_fin="2024-01-31",
            metadata={"v": 1},
            records=[],
            session=db_session,
        )
        run2 = save_run(
            run_label="dup_label",
            fecha_inicio="2024-02-01",
            fecha_fin="2024-02-28",
            metadata={"v": 2},
            records=[{"demandado": "EXTRA", "decision": "accepted"}],
            session=db_session,
        )
        assert run1.id == run2.id
        # Original metadata preserved (idempotent — does not update)
        assert run1.metadata_["v"] == 1

    def test_empty_emails_stored_as_none(self, db_session):
        # In repository.py: emails if emails else None → [] becomes None
        run = save_run(
            run_label="empty_emails",
            fecha_inicio="2024-01-01",
            fecha_fin="2024-01-31",
            metadata={},
            records=[{"demandado": "ACME", "decision": "accepted", "emails_encontrados": []}],
            session=db_session,
        )
        pr = db_session.query(PipelineRecord).filter(PipelineRecord.run_id == run.id).first()
        assert pr.emails_encontrados is None, (
            "Empty list [] is stored as NULL — distinguish 'no emails' from 'not enriched'"
        )

    def test_emails_with_values_stored_as_array(self, db_session):
        run = save_run(
            run_label="emails_array",
            fecha_inicio="2024-01-01",
            fecha_fin="2024-01-31",
            metadata={},
            records=[{"demandado": "ACME", "decision": "accepted", "emails_encontrados": ["a@b.com"]}],
            session=db_session,
        )
        pr = db_session.query(PipelineRecord).filter(PipelineRecord.run_id == run.id).first()
        assert pr.emails_encontrados == ["a@b.com"]
