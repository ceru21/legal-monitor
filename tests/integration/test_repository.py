"""Integration tests for db/repository.py."""
from __future__ import annotations

import pytest
from db.models import Contact, PipelineRecord, Run
from db.repository import query_contacts_by_name, save_run


@pytest.mark.integration
class TestQueryContactsByName:
    def test_returns_emails_for_existing_name(self, db_session):
        contact = Contact(
            razon_social="ACME S.A.S.",
            razon_social_normalizada="acme",
            correo_comercial="contacto@acme.com",
            source_label="test",
        )
        db_session.add(contact)
        db_session.flush()
        result = query_contacts_by_name("acme", db_session)
        assert "contacto@acme.com" in result

    def test_returns_empty_for_unknown_name(self, db_session):
        result = query_contacts_by_name("empresa_que_no_existe_xyz", db_session)
        assert result == []

    def test_filters_none_emails(self, db_session):
        contact = Contact(
            razon_social="INVERSIONES ABC",
            razon_social_normalizada="inversiones abc",
            correo_comercial=None,
            source_label="test",
        )
        db_session.add(contact)
        db_session.flush()
        result = query_contacts_by_name("inversiones abc", db_session)
        assert result == []

    def test_returns_multiple_emails(self, db_session):
        for email in ["a@acme.com", "b@acme.com"]:
            db_session.add(Contact(
                razon_social="ACME S.A.S.",
                razon_social_normalizada="acme",
                correo_comercial=email,
                source_label="test",
            ))
        db_session.flush()
        result = query_contacts_by_name("acme", db_session)
        assert "a@acme.com" in result
        assert "b@acme.com" in result


@pytest.mark.integration
class TestSaveRun:
    def _base_records(self):
        return [
            {
                "despacho_id": "DESP001",
                "demandado": "ACME S.A.S.",
                "decision": "accepted",
                "match_camara": True,
                "emails_encontrados": ["a@b.com"],
            }
        ]

    def test_save_run_creates_run_and_records(self, db_session):
        run = save_run(
            run_label="test_run_001",
            fecha_inicio="2024-01-01",
            fecha_fin="2024-01-31",
            metadata={"enrichment_enabled": True},
            records=self._base_records(),
            session=db_session,
        )
        assert run.id is not None
        records = db_session.query(PipelineRecord).filter(PipelineRecord.run_id == run.id).all()
        assert len(records) == 1

    def test_save_run_idempotent(self, db_session):
        run1 = save_run(
            run_label="test_run_idem",
            fecha_inicio="2024-01-01",
            fecha_fin="2024-01-31",
            metadata={},
            records=self._base_records(),
            session=db_session,
        )
        run2 = save_run(
            run_label="test_run_idem",
            fecha_inicio="2024-01-01",
            fecha_fin="2024-01-31",
            metadata={},
            records=self._base_records(),
            session=db_session,
        )
        assert run1.id == run2.id

    def test_save_run_empty_records(self, db_session):
        run = save_run(
            run_label="test_run_empty",
            fecha_inicio="2024-01-01",
            fecha_fin="2024-01-31",
            metadata={},
            records=[],
            session=db_session,
        )
        assert run.id is not None
        count = db_session.query(PipelineRecord).filter(PipelineRecord.run_id == run.id).count()
        assert count == 0

    def test_cascade_delete_run_removes_records(self, db_session):
        run = save_run(
            run_label="test_run_cascade",
            fecha_inicio="2024-01-01",
            fecha_fin="2024-01-31",
            metadata={},
            records=self._base_records(),
            session=db_session,
        )
        run_id = run.id
        db_session.delete(run)
        db_session.flush()
        count = db_session.query(PipelineRecord).filter(PipelineRecord.run_id == run_id).count()
        assert count == 0

    def test_match_camara_none_stored_as_null(self, db_session):
        # FIXED #3: match_camara=None now stored as NULL, distinguishing
        # 'not enriched' (NULL) from 'no match found' (False)
        record = {
            "despacho_id": "DESP002",
            "demandado": "EMPRESA",
            "decision": "accepted",
            "match_camara": None,
            "emails_encontrados": [],
        }
        run = save_run(
            run_label="test_run_none_fixed",
            fecha_inicio="2024-01-01",
            fecha_fin="2024-01-31",
            metadata={},
            records=[record],
            session=db_session,
        )
        pr = db_session.query(PipelineRecord).filter(PipelineRecord.run_id == run.id).first()
        assert pr.match_camara is None
