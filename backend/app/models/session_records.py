"""SQLAlchemy persistence models for Klinia MVP sessions."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Clinic(Base):
    __tablename__ = "clinics"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="clinic")
    patients: Mapped[list["Patient"]] = relationship(back_populates="clinic")
    sessions: Mapped[list["Session"]] = relationship(back_populates="clinic")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    clinic: Mapped[Clinic] = relationship(back_populates="users")
    sessions: Mapped[list["Session"]] = relationship(back_populates="dentist")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    initials: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    national_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    occupation: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    referred_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    clinic: Mapped[Clinic] = relationship(back_populates="patients")
    sessions: Mapped[list["Session"]] = relationship(back_populates="patient")
    medical_history: Mapped[Optional["PatientMedicalHistory"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan", uselist=False
    )


class PatientMedicalHistory(Base):
    __tablename__ = "patient_medical_histories"

    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), primary_key=True)
    has_chronic_illness: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    chronic_illness_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    takes_regular_medication: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    regular_medication_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    has_drug_allergy: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    drug_allergy_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    has_contagious_disease: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    contagious_disease_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    patient: Mapped[Patient] = relationship(back_populates="medical_history")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"), nullable=False, index=True)
    patient_id: Mapped[Optional[str]] = mapped_column(ForeignKey("patients.id"), nullable=True, index=True)
    dentist_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    session_type: Mapped[Literal["clinical_note", "perio"]] = mapped_column(
        String(32), default="clinical_note", server_default="clinical_note", nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    current_stage: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    review_snapshot_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    clinic: Mapped[Clinic] = relationship(back_populates="sessions")
    patient: Mapped[Optional[Patient]] = relationship(back_populates="sessions")
    dentist: Mapped[Optional[User]] = relationship(back_populates="sessions")
    transcripts: Mapped[list["Transcript"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    clinical_notes: Mapped[list["ClinicalNote"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    code_suggestions: Mapped[list["CodeSuggestion"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), default="voice", nullable=False)
    utterances_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    session: Mapped[Session] = relationship(back_populates="transcripts")


class ClinicalNote(Base):
    __tablename__ = "clinical_notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False, index=True)
    draft_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    approved_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    session: Mapped[Session] = relationship(back_populates="clinical_notes")


class ProcedureCode(Base):
    __tablename__ = "procedure_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    source_year: Mapped[str] = mapped_column(String(16), nullable=False)

    suggestions: Mapped[list["CodeSuggestion"]] = relationship(back_populates="procedure_code")


class CodeSuggestion(Base):
    __tablename__ = "code_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False, index=True)
    procedure_code_id: Mapped[Optional[int]] = mapped_column(ForeignKey("procedure_codes.id"), nullable=True, index=True)
    match_state: Mapped[str] = mapped_column(String(96), nullable=False)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    accepted_by_user: Mapped[bool] = mapped_column(default=False, nullable=False)

    session: Mapped[Session] = relationship(back_populates="code_suggestions")
    procedure_code: Mapped[Optional[ProcedureCode]] = relationship(back_populates="suggestions")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    user: Mapped[Optional[User]] = relationship(back_populates="audit_logs")
    session: Mapped[Session] = relationship(back_populates="audit_logs")


Index("ix_patients_clinic_external_id", Patient.clinic_id, Patient.external_id)
Index("ix_sessions_clinic_status", Session.clinic_id, Session.status)
Index("ix_audit_logs_session_timestamp", AuditLog.session_id, AuditLog.timestamp)

# Backward-compatible names for existing API/repository code.
SessionRecord = Session
TranscriptRecord = Transcript
ClinicalNoteRecord = ClinicalNote
AuditLogRecord = AuditLog
