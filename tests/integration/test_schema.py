"""Integration tests: schema creation is idempotent and has expected tables/indexes."""
from __future__ import annotations

import pytest
from sqlalchemy import inspect, text


@pytest.mark.integration
class TestSchema:
    def test_create_all_idempotent(self, test_engine):
        """Running create_all twice should not raise."""
        from db import Base
        import db.models  # noqa: F401
        Base.metadata.create_all(test_engine)
        Base.metadata.create_all(test_engine)  # second call — must not raise

    def test_contacts_table_exists(self, test_engine):
        inspector = inspect(test_engine)
        assert "contacts" in inspector.get_table_names()

    def test_runs_table_exists(self, test_engine):
        inspector = inspect(test_engine)
        assert "runs" in inspector.get_table_names()

    def test_pipeline_records_table_exists(self, test_engine):
        inspector = inspect(test_engine)
        assert "pipeline_records" in inspector.get_table_names()

    def test_contacts_normalized_index_exists(self, test_engine):
        inspector = inspect(test_engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("contacts")}
        assert "ix_contacts_normalized" in indexes

    def test_pipeline_records_run_id_index_exists(self, test_engine):
        inspector = inspect(test_engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("pipeline_records")}
        assert "ix_pipeline_records_run_id" in indexes

    def test_pipeline_records_decision_index_exists(self, test_engine):
        inspector = inspect(test_engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("pipeline_records")}
        assert "ix_pipeline_records_decision" in indexes

    def test_pipeline_records_demandado_index_exists(self, test_engine):
        inspector = inspect(test_engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("pipeline_records")}
        assert "ix_pipeline_records_demandado" in indexes
