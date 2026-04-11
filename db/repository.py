"""Data access functions for the legal-monitor pipeline."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.models import Contact, PipelineRecord, Run

logger = logging.getLogger("legal_monitor.db.repository")


def query_contacts_by_name(normalized_name: str, session: Session) -> list[str]:
    """Return list of unique emails for a given normalized company name."""
    try:
        rows = (
            session.query(Contact.correo_comercial)
            .filter(Contact.razon_social_normalizada == normalized_name)
            .filter(Contact.correo_comercial.isnot(None))
            .all()
        )
        return [r.correo_comercial for r in rows if r.correo_comercial]
    except SQLAlchemyError:
        logger.warning("DB query failed for name lookup; returning empty result")
        return []


def save_run(
    run_label: str,
    fecha_inicio: str,
    fecha_fin: str,
    metadata: dict[str, Any],
    records: list[dict[str, Any]],
    session: Session,
) -> Run:
    """Persist a pipeline run and its records. Idempotent: skips if run_label exists."""
    try:
        existing = session.query(Run).filter(Run.run_label == run_label).first()
        if existing:
            return existing

        run = Run(
            run_label=run_label,
            fecha_inicio=date.fromisoformat(fecha_inicio),
            fecha_fin=date.fromisoformat(fecha_fin),
            metadata_=metadata,
        )
        session.add(run)
        session.flush()  # get run.id

        for record in records:
            emails = record.get("emails_encontrados") or []
            pr = PipelineRecord(
                run_id=run.id,
                despacho_id=record.get("despacho_id"),
                demandado=record.get("demandado"),
                decision=record.get("decision"),
                match_camara=record.get("match_camara"),
                emails_encontrados=emails if emails else None,
                full_record=record,
            )
            session.add(pr)

        session.commit()
        return run
    except SQLAlchemyError:
        session.rollback()
        raise RuntimeError("Failed to persist pipeline run to database") from None
