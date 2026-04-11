"""QA-specific fixtures for the legal-monitor QA suite."""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = PROJECT_ROOT / "scripts"
for _p in (str(PROJECT_ROOT), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from models import DetailDocument, ParsedRow, Publication


# ---------------------------------------------------------------------------
# DB cleanup after each QA test that commits to real DB
# ---------------------------------------------------------------------------


@pytest.fixture
def qa_db_cleanup(test_engine):
    """Wipe all tables after each test that commits directly to the real DB."""
    yield
    with test_engine.connect() as conn:
        conn.execute(text("DELETE FROM pipeline_records"))
        conn.execute(text("DELETE FROM runs"))
        conn.execute(text("DELETE FROM contacts"))
        conn.commit()


# ---------------------------------------------------------------------------
# Mock portal + PDF — no HTTP, no real PDF download
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_portal_and_pdf(monkeypatch, tmp_path):
    """Patch all external I/O so run_pipeline runs without HTTP or real PDFs."""
    import run_search

    monkeypatch.setattr(
        run_search,
        "load_scope_despachos",
        lambda: [{"id": "050013103001", "nombre": "Juzgado 1 Civil Circuito Medellin"}],
    )

    class MockPortalClient:
        def __init__(self):
            pass

        def search_html(self, fecha_inicio, fecha_fin, id_despacho=None):
            return "<html><body>mock</body></html>"

        def extract_publications(self, html_text):
            return [
                Publication(
                    publication_id="PUB-TEST-001",
                    despacho="Juzgado 1 Civil Circuito Medellin",
                    fecha_publicacion="2026-04-11",
                    titulo_publicacion="Estado 2026-04-11",
                    publication_url="http://mock/pub/001",
                    pdf_url="http://mock/pdf/001.pdf",
                )
            ]

        def fetch_detail_documents(self, url):
            return [
                DetailDocument(
                    label="estado_planilla.pdf",
                    url="http://mock/pdf/estado_planilla.pdf",
                    is_primary_candidate=True,
                )
            ]

        def download_document(self, url, path):
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"%PDF-1.4 mock")

    monkeypatch.setattr(run_search, "PortalClient", MockPortalClient)

    def _mock_parse_pdf(pdf_path):
        return [
            ParsedRow(
                pdf_fingerprint="abc123",
                pdf_page_number=1,
                row_index=0,
                raw_columns=["2026-001", "ejecutivo", "admite demanda", "ACME S.A.S.", "Juan Garcia"],
                texto_fila_original="2026-001 ejecutivo admite demanda ACME S.A.S. Juan Garcia",
                radicado_raw="2026-001",
                radicado_normalizado="2026-001",
                tipo_proceso="ejecutivo",
                actuacion="admite demanda",
                demandante="Juan Garcia",
                demandado="ACME S.A.S.",
                parse_mode="column_coordinates",
                parse_confidence=0.95,
            ),
            ParsedRow(
                pdf_fingerprint="abc123",
                pdf_page_number=1,
                row_index=1,
                raw_columns=["2026-002", "ordinario", "notificacion auto", "EMPRESA DESCONOCIDA", "Maria Lopez"],
                texto_fila_original="2026-002 ordinario notificacion auto EMPRESA DESCONOCIDA Maria Lopez",
                radicado_raw="2026-002",
                radicado_normalizado="2026-002",
                tipo_proceso="ordinario",
                actuacion="notificacion auto",
                demandante="Maria Lopez",
                demandado="EMPRESA DESCONOCIDA",
                parse_mode="column_coordinates",
                parse_confidence=0.90,
            ),
        ]

    monkeypatch.setattr(run_search, "parse_pdf", _mock_parse_pdf)

    class MockBlacklistFilter:
        @classmethod
        def from_yaml(cls, path):
            return cls()

        def apply(self, records):
            return records

    monkeypatch.setattr(run_search, "BlacklistFilter", MockBlacklistFilter)

    return tmp_path


# ---------------------------------------------------------------------------
# Seeded contacts in test DB
# ---------------------------------------------------------------------------


@pytest.fixture
def seeded_contacts(db_session):
    """Insert 5 Contact rows into the test DB via ORM. Returns the session."""
    from db.models import Contact
    from enrich_contacts import normalize_company_name

    companies = [
        ("ACME S.A.S.", "contacto@acme.com"),
        ("GLOBAL TRADE LTDA", "info@globaltrade.com"),
        ("TECNOLOGIAS DEL FUTURO S.A.", "ventas@tecfuturo.co"),
        ("INVERSIONES ABC", None),
        ("DISTRIBUIDORA XYZ S A", "ventas@xyz.com"),
    ]
    for razon, email in companies:
        db_session.add(
            Contact(
                razon_social=razon,
                razon_social_normalizada=normalize_company_name(razon),
                correo_comercial=email,
                source_label="test_qa",
            )
        )
    db_session.flush()
    return db_session


# ---------------------------------------------------------------------------
# Realistic record (full pipeline output shape including enrichment)
# ---------------------------------------------------------------------------


@pytest.fixture
def realistic_record():
    """A record shaped like merge_record_context + enrich_record_from_db output."""
    return {
        # run context
        "run_label": "medellin_civil_circuito_2026-04-11_a_2026-04-11_20260411T120000Z",
        "fecha_inicio": "2026-04-11",
        "fecha_fin": "2026-04-11",
        # despacho
        "despacho_id": "050013103001",
        "despacho": "Juzgado 1 Civil Circuito Medellin",
        # publication
        "publication_id": "PUB-TEST-001",
        "fecha_publicacion": "2026-04-11",
        "titulo_publicacion": "Estado 2026-04-11",
        "publication_url": "http://mock/pub/001",
        # pdf
        "pdf_label": "estado_planilla.pdf",
        "pdf_url": "http://mock/pdf/estado_planilla.pdf",
        "pdf_path": "/tmp/pdfs/050013103001_estado_planilla.pdf",
        "pdf_fingerprint": "abc123",
        "pdf_page_number": 1,
        "row_index": 0,
        # row data
        "raw_columns": ["2026-001", "ejecutivo", "admite demanda", "ACME S.A.S.", "Juan Garcia"],
        "texto_fila_original": "2026-001 ejecutivo admite demanda ACME S.A.S. Juan Garcia",
        "radicado_raw": "2026-001",
        "radicado_normalizado": "2026-001",
        "tipo_proceso": "ejecutivo",
        "actuacion": "admite demanda",
        "demandante": "Juan Garcia",
        "demandado": "ACME S.A.S.",
        "anotacion": None,
        "revision_manual": "No",
        "parse_mode": "column_coordinates",
        "parse_confidence": 0.95,
        # decision
        "decision": "accepted",
        "match_reason": "process_type",
        "process_type_match": "ejecutivo",
        "actuacion_match": "admite demanda",
        "process_type_confidence": 0.95,
        "actuacion_confidence": 0.92,
        # enrichment
        "match_camara": True,
        "emails_encontrados": ["contacto@acme.com"],
        "demandado_normalizado_match": "acme",
        # blacklist
        "blacklisted": False,
        "blacklist_match": None,
        # drafts (not created)
        "draft_id": None,
        "draft_status": None,
        "draft_email_to": None,
    }


# ---------------------------------------------------------------------------
# Fake publication
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_publication():
    return Publication(
        publication_id="PUB-FAKE-001",
        despacho="Juzgado 1 Civil Circuito Medellin",
        fecha_publicacion="2026-04-11",
        titulo_publicacion="Estado 2026-04-11",
        publication_url="http://mock/pub/001",
        pdf_url="http://mock/pdf/001.pdf",
    )


# ---------------------------------------------------------------------------
# Fake parsed rows
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_parsed_rows():
    return [
        ParsedRow(
            pdf_fingerprint="abc123",
            pdf_page_number=1,
            row_index=0,
            raw_columns=["2026-001", "ejecutivo", "admite demanda", "ACME S.A.S.", "Juan Garcia"],
            texto_fila_original="2026-001 ejecutivo admite demanda ACME S.A.S. Juan Garcia",
            radicado_raw="2026-001",
            radicado_normalizado="2026-001",
            tipo_proceso="ejecutivo",
            actuacion="admite demanda",
            demandante="Juan Garcia",
            demandado="ACME S.A.S.",
            parse_mode="column_coordinates",
            parse_confidence=0.95,
        ),
        ParsedRow(
            pdf_fingerprint="abc123",
            pdf_page_number=1,
            row_index=1,
            raw_columns=["2026-002", "ordinario", "notificacion auto", "EMPRESA DESCONOCIDA", "Maria Lopez"],
            texto_fila_original="2026-002 ordinario notificacion auto EMPRESA DESCONOCIDA Maria Lopez",
            radicado_raw="2026-002",
            radicado_normalizado="2026-002",
            tipo_proceso="ordinario",
            actuacion="notificacion auto",
            demandante="Maria Lopez",
            demandado="EMPRESA DESCONOCIDA",
            parse_mode="column_coordinates",
            parse_confidence=0.90,
        ),
    ]
