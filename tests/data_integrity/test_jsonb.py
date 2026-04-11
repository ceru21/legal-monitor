"""Data integrity: JSONB fields preserve original data."""
from __future__ import annotations

import pytest
from db.models import Contact, PipelineRecord, Run
from db.repository import save_run


@pytest.mark.integration
class TestJsonbFields:
    def test_raw_data_preserves_all_columns(self, db_session):
        raw = {"razon_social": "ACME", "correo_comercial": "a@b.com", "extra_col": "val", "nit": "123"}
        contact = Contact(
            razon_social="ACME",
            razon_social_normalizada="acme",
            correo_comercial="a@b.com",
            source_label="test",
            raw_data=raw,
        )
        db_session.add(contact)
        db_session.flush()
        db_session.refresh(contact)
        assert contact.raw_data["extra_col"] == "val"
        assert contact.raw_data["nit"] == "123"

    def test_metadata_preserves_nested_struct(self, db_session):
        meta = {"enrichment_enabled": True, "nested": {"key": "value"}, "count": 42}
        run = Run(
            run_label="test_meta",
            fecha_inicio="2024-01-01",
            fecha_fin="2024-01-31",
            metadata_=meta,
        )
        db_session.add(run)
        db_session.flush()
        db_session.refresh(run)
        assert run.metadata_["nested"]["key"] == "value"
        assert run.metadata_["count"] == 42

    def test_full_record_preserves_all_fields(self, db_session):
        full = {
            "despacho_id": "D001",
            "demandado": "ACME S.A.S.",
            "decision": "accepted",
            "match_camara": True,
            "emails_encontrados": ["a@b.com"],
            "custom_field": "custom_value",
        }
        run = save_run(
            run_label="test_full_record",
            fecha_inicio="2024-01-01",
            fecha_fin="2024-01-31",
            metadata={},
            records=[full],
            session=db_session,
        )
        pr = db_session.query(PipelineRecord).filter(PipelineRecord.run_id == run.id).first()
        assert pr.full_record["custom_field"] == "custom_value"
        assert pr.full_record["decision"] == "accepted"
