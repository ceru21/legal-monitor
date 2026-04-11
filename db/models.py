from __future__ import annotations

from datetime import datetime, date
from typing import List, Optional

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    razon_social: Mapped[str] = mapped_column(Text, nullable=False)
    razon_social_normalizada: Mapped[str] = mapped_column(Text, nullable=False)
    correo_comercial: Mapped[Optional[str]] = mapped_column(Text)
    source_label: Mapped[str] = mapped_column(Text, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_contacts_normalized", "razon_social_normalizada"),
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_label: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)

    records: Mapped[List[PipelineRecord]] = relationship(
        "PipelineRecord", back_populates="run", cascade="all, delete-orphan"
    )


class PipelineRecord(Base):
    __tablename__ = "pipeline_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    despacho_id: Mapped[Optional[str]] = mapped_column(Text)
    demandado: Mapped[Optional[str]] = mapped_column(Text)
    decision: Mapped[Optional[str]] = mapped_column(Text)
    match_camara: Mapped[Optional[bool]] = mapped_column(Boolean)
    emails_encontrados: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text))
    full_record: Mapped[Optional[dict]] = mapped_column(JSONB)

    run: Mapped[Run] = relationship("Run", back_populates="records")

    __table_args__ = (
        Index("ix_pipeline_records_run_id", "run_id"),
        Index("ix_pipeline_records_decision", "decision"),
        Index("ix_pipeline_records_demandado", "demandado"),
    )
