"""Session persistence models for the MVP workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionRecord(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    clinic_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    patient_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="created", nullable=False, index=True)
    current_stage: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    transcripts: Mapped[list["TranscriptRecord"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
    clinical_notes: Mapped[list["ClinicalNoteRecord"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
    review_decisions: Mapped[list["ReviewDecisionRecord"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
    export_payloads: Mapped[list["ExportPayloadRecord"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )
    audit_logs: Mapped[list["AuditLogRecord"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class TranscriptRecord(Base):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), default="audio", nullable=False)
    utterances_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    session: Mapped[SessionRecord] = relationship(back_populates="transcripts")


class ClinicalNoteRecord(Base):
    __tablename__ = "clinical_notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False, index=True)
    note_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    note_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    session: Mapped[SessionRecord] = relationship(back_populates="clinical_notes")


class ReviewDecisionRecord(Base):
    __tablename__ = "review_decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False, index=True)
    reviewer_user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    approved: Mapped[bool] = mapped_column(default=False, nullable=False)
    selected_codes_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    decision_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    session: Mapped[SessionRecord] = relationship(back_populates="review_decisions")


class ExportPayloadRecord(Base):
    __tablename__ = "export_payloads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    session: Mapped[SessionRecord] = relationship(back_populates="export_payloads")


class AuditLogRecord(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False, index=True)
    actor_user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    session: Mapped[SessionRecord] = relationship(back_populates="audit_logs")


Index("ix_sessions_clinic_status", SessionRecord.clinic_id, SessionRecord.status)
