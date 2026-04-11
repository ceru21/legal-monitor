"""Integration tests for db/import_contacts.py."""
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.integration
class TestImportContacts:
    def test_import_sample_file(self, patch_session_local, sample_contacts_file):
        from db.import_contacts import import_contacts
        total = import_contacts(sample_contacts_file, label="test_import")
        # 5 rows in fixture, 1 has empty razon_social after normalize? No — INVERSIONES ABC normalizes fine
        # INVERSIONES ABC → "inversiones abc" (not empty), so expect 5
        # But INVERSIONES ABC has no correo — that's ok, correo is nullable
        assert total == 5

    def test_normalized_razon_social_populated(self, patch_session_local, sample_contacts_file, test_engine):
        from db.import_contacts import import_contacts
        from db.models import Contact
        from sqlalchemy.orm import sessionmaker
        import_contacts(sample_contacts_file, label="test_normalized")
        Session = sessionmaker(bind=test_engine)
        with Session() as s:
            contacts = s.query(Contact).filter(Contact.source_label == "test_normalized").all()
            for c in contacts:
                assert c.razon_social_normalizada is not None
                assert len(c.razon_social_normalizada) > 0

    def test_reimport_replace_true(self, patch_session_local, sample_contacts_file, test_engine):
        from db.import_contacts import import_contacts
        from db.models import Contact
        from sqlalchemy.orm import sessionmaker
        import_contacts(sample_contacts_file, label="test_replace")
        import_contacts(sample_contacts_file, label="test_replace", replace=True)
        Session = sessionmaker(bind=test_engine)
        with Session() as s:
            count = s.query(Contact).filter(Contact.source_label == "test_replace").count()
        assert count == 5  # replaced, not duplicated

    def test_reimport_replace_false_duplicates(self, patch_session_local, sample_contacts_file, test_engine):
        from db.import_contacts import import_contacts
        from db.models import Contact
        from sqlalchemy.orm import sessionmaker
        import_contacts(sample_contacts_file, label="test_nodup")
        import_contacts(sample_contacts_file, label="test_nodup", replace=False)
        Session = sessionmaker(bind=test_engine)
        with Session() as s:
            count = s.query(Contact).filter(Contact.source_label == "test_nodup").count()
        assert count == 10  # duplicated

    def test_empty_file_returns_zero(self, patch_session_local):
        from db.import_contacts import import_contacts
        empty_file = FIXTURES / "sample_contacts_empty.txt"
        total = import_contacts(empty_file, label="test_empty")
        assert total == 0
