"""Repository for MVP session persistence."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session as OrmSession

from app.models.session_records import (
    AuditLog,
    ClinicalNote,
    Clinic,
    CodeSuggestion,
    Patient,
    ProcedureCode,
    Session,
    Transcript,
    User,
)
from app.pipeline.types import ClinicalNoteDraft, CodeSuggestionBundle, PipelineResult, PipelineStatus


class SessionRepository:
    def __init__(self, db: OrmSession) -> None:
        self.db = db

    def ensure_clinic(self, clinic_id: str, *, name: Optional[str] = None) -> Clinic:
        record = self.db.get(Clinic, clinic_id)
        if record is None:
            record = Clinic(id=clinic_id, name=name or clinic_id)
            self.db.add(record)
            self.db.flush()
        return record

    def ensure_user(
        self,
        user_id: str,
        *,
        clinic_id: str,
        role: str = "dentist",
        email: Optional[str] = None,
    ) -> User:
        self.ensure_clinic(clinic_id)
        record = self.db.get(User, user_id)
        if record is None:
            record = User(
                id=user_id,
                clinic_id=clinic_id,
                role=role,
                email=email or f"{user_id}@local.klinia",
                password_hash="",
            )
            self.db.add(record)
            self.db.flush()
        return record

    def ensure_patient(
        self,
        patient_id: str,
        *,
        clinic_id: str,
        external_id: Optional[str] = None,
        initials: Optional[str] = None,
    ) -> Patient:
        self.ensure_clinic(clinic_id)
        record = self.db.get(Patient, patient_id)
        if record is None:
            record = Patient(
                id=patient_id,
                clinic_id=clinic_id,
                external_id=external_id,
                initials=initials,
            )
            self.db.add(record)
            self.db.flush()
        return record

    def create_patient(
        self,
        patient_id: str,
        *,
        clinic_id: str,
        display_name: Optional[str] = None,
        external_id: Optional[str] = None,
        national_id: Optional[str] = None,
        date_of_birth: Optional[date] = None,
        occupation: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        referred_by: Optional[str] = None,
    ) -> Patient:
        self.ensure_clinic(clinic_id)
        if external_id:
            existing = self.db.scalar(
                select(Patient).where(
                    Patient.clinic_id == clinic_id,
                    Patient.external_id == external_id,
                )
            )
            if existing is not None:
                raise ValueError("Bu dosya numarası aynı klinikte zaten kullanılıyor.")
        record = Patient(
            id=patient_id,
            clinic_id=clinic_id,
            display_name=display_name,
            external_id=external_id,
            national_id=national_id,
            date_of_birth=date_of_birth,
            occupation=occupation,
            address=address,
            phone=phone,
            email=email,
            referred_by=referred_by,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def attach_patient_to_session(
        self,
        session_id: str,
        patient_id: str,
        *,
        clinic_id: str,
    ) -> Session:
        session = self._require_session_in_clinic(session_id, clinic_id)
        self._require_patient_in_clinic(patient_id, clinic_id)
        session.patient_id = patient_id
        self.db.flush()
        return session

    def upsert_session(
        self,
        session_id: str,
        *,
        status: str,
        current_stage: Optional[str] = None,
        clinic_id: str,
        patient_id: Optional[str] = None,
        dentist_id: Optional[str] = None,
        session_type: Optional[Literal["clinical_note", "perio"]] = None,
    ) -> Session:
        self.ensure_clinic(clinic_id)
        if dentist_id is not None:
            self.ensure_user(dentist_id, clinic_id=clinic_id)
        if patient_id is not None:
            self._require_patient_in_clinic(patient_id, clinic_id)
        record = self.db.get(Session, session_id)
        mapped_status = _session_status(status)
        if record is None:
            record = Session(
                id=session_id,
                clinic_id=clinic_id,
                patient_id=patient_id,
                dentist_id=dentist_id,
                status=mapped_status,
                session_type=session_type or "clinical_note",
                current_stage=current_stage,
            )
            self.db.add(record)
        else:
            if record.clinic_id != clinic_id:
                raise PermissionError("Session farklı kliniğe ait.")
            record.status = mapped_status
            record.current_stage = current_stage
            if session_type is not None:
                record.session_type = session_type
            if patient_id is not None:
                record.patient_id = patient_id
            if dentist_id is not None:
                record.dentist_id = dentist_id
        self.db.flush()
        return record

    def save_pipeline_result(
        self,
        result: PipelineResult,
        *,
        clinic_id: str,
        actor_user_id: Optional[str],
        transcript_source: str,
        patient_id: Optional[str] = None,
    ) -> Session:
        self.upsert_session(
            result.session_id,
            status=result.status.value,
            current_stage=result.stopped_at_stage,
            clinic_id=clinic_id,
            dentist_id=actor_user_id,
            patient_id=patient_id,
        )
        if result.speaker_labelled_transcript is not None:
            self.save_transcript(
                result.session_id,
                [
                    {
                        "speaker_id": utterance.speaker_id,
                        "text": utterance.text,
                        "start_sec": utterance.start_sec,
                        "end_sec": utterance.end_sec,
                    }
                    for utterance in result.speaker_labelled_transcript.utterances
                ],
                source=transcript_source,
                clinic_id=clinic_id,
                actor_user_id=actor_user_id,
            )
        if result.clinical_note is not None:
            self.save_clinical_note(
                result.session_id,
                result.clinical_note,
                clinic_id=clinic_id,
                actor_user_id=actor_user_id,
            )
        if result.code_suggestions:
            self.save_code_suggestions(result.session_id, result.code_suggestions, clinic_id=clinic_id)
        return self.latest_session(result.session_id, clinic_id=clinic_id)

    def save_transcript(
        self,
        session_id: str,
        utterances: list[dict],
        *,
        source: str = "voice",
        clinic_id: str,
        actor_user_id: Optional[str] = None,
    ) -> Transcript:
        self.upsert_session(
            session_id,
            status="draft",
            current_stage="transcript",
            clinic_id=clinic_id,
            dentist_id=actor_user_id,
        )
        record = Transcript(
            session_id=session_id,
            source=source,
            utterances_json=utterances,
        )
        self.db.add(record)
        self.add_audit_log(
            user_id=actor_user_id,
            session_id=session_id,
            clinic_id=clinic_id,
            action="transcript_saved",
            entity_type="transcript",
            entity_id=None,
            source="voice" if source.startswith("audio") else "manual",
            metadata_json={"utterance_count": len(utterances), "transcript_source": source},
        )
        self.db.flush()
        return record

    def save_clinical_note(
        self,
        session_id: str,
        note: ClinicalNoteDraft,
        *,
        status: str = "draft",
        clinic_id: str,
        actor_user_id: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> ClinicalNote:
        self.upsert_session(
            session_id,
            status="approved" if status == "approved" else "draft",
            current_stage="dentist_review",
            clinic_id=clinic_id,
            dentist_id=actor_user_id,
        )
        note_json = note.model_dump(mode="json")
        record = self.db.scalar(
            select(ClinicalNote)
            .where(ClinicalNote.session_id == session_id)
            .order_by(ClinicalNote.id.asc())
        )
        if record is None:
            record = ClinicalNote(
                session_id=session_id,
                draft_json=note_json,
                approved_json=note_json if status == "approved" else None,
                status=status,
                model_version=model_version,
            )
            self.db.add(record)
            self.db.flush()
            audit_action = "clinical_note_saved" if status == "draft" else "clinical_note_approved"
        else:
            previous_draft_json = record.draft_json
            previous_status = record.status
            self.add_audit_log(
                user_id=actor_user_id,
                session_id=session_id,
                clinic_id=clinic_id,
                action="draft_replaced",
                entity_type="clinical_note",
                entity_id=str(record.id),
                source="ai" if status == "draft" else "manual",
                metadata_json={
                    "previous_status": previous_status,
                    "new_status": status,
                    "previous_draft_json": previous_draft_json,
                },
            )
            record.draft_json = note_json
            record.approved_json = note_json if status == "approved" else None
            record.status = status
            record.model_version = model_version
            audit_action = "clinical_note_saved" if status == "draft" else "clinical_note_approved"
        self.add_audit_log(
            user_id=actor_user_id,
            session_id=session_id,
            clinic_id=clinic_id,
            action=audit_action,
            entity_type="clinical_note",
            entity_id=str(record.id) if record.id is not None else None,
            source="ai" if status == "draft" else "manual",
            metadata_json={"status": status},
        )
        self.db.flush()
        return record

    def save_code_suggestions(
        self,
        session_id: str,
        bundles: list[CodeSuggestionBundle],
        *,
        clinic_id: str,
    ) -> list[CodeSuggestion]:
        self._require_session_in_clinic(session_id, clinic_id)
        for existing in self.db.scalars(select(CodeSuggestion).where(CodeSuggestion.session_id == session_id)):
            self.db.delete(existing)
        self.db.flush()
        records: list[CodeSuggestion] = []
        for bundle in bundles:
            explanations_by_code = {explanation.code: explanation for explanation in bundle.explanations}
            states_by_code = {result.code: result.match_state.value for result in bundle.match_results}
            for candidate in bundle.candidates:
                procedure_code = self._upsert_procedure_code(
                    code=candidate.code,
                    title=candidate.procedure_name,
                    category=candidate.category,
                    source_year=candidate.source_version,
                )
                explanation = explanations_by_code.get(candidate.code)
                record = CodeSuggestion(
                    session_id=session_id,
                    procedure_code_id=procedure_code.id,
                    match_state=states_by_code.get(candidate.code, "needs_review"),
                    explanation=explanation.fit_reason if explanation is not None else None,
                    accepted_by_user=False,
                )
                self.db.add(record)
                records.append(record)
        self.db.flush()
        return records

    def save_review_approval(
        self,
        session_id: str,
        *,
        approved: bool,
        selected_codes: list[str],
        reviewer_user_id: Optional[str],
        export_payload: Optional[Any],
        clinic_id: str,
    ) -> None:
        self.upsert_session(
            session_id,
            status="approved" if approved else "draft",
            current_stage="ready_for_export" if approved else "dentist_review",
            clinic_id=clinic_id,
            dentist_id=reviewer_user_id,
        )
        if selected_codes:
            self._mark_accepted_codes(session_id, selected_codes, clinic_id=clinic_id)
        self.add_audit_log(
            user_id=reviewer_user_id,
            session_id=session_id,
            clinic_id=clinic_id,
            action="doctor_review_approved" if approved else "doctor_review_rejected",
            entity_type="session",
            entity_id=session_id,
            source="manual",
            metadata_json={"selected_codes": selected_codes},
        )
        if approved and export_payload is not None:
            self.add_audit_log(
                user_id=reviewer_user_id,
                session_id=session_id,
                clinic_id=clinic_id,
                action="export_payload_created",
                entity_type="export_payload",
                entity_id=session_id,
                source="manual",
                metadata_json=export_payload.model_dump(mode="json"),
            )
        self.db.flush()

    def add_audit_log(
        self,
        *,
        user_id: Optional[str],
        session_id: str,
        clinic_id: str,
        action: str,
        entity_type: str,
        entity_id: Optional[str],
        source: str,
        metadata_json: dict,
    ) -> AuditLog:
        self._require_session_in_clinic(session_id, clinic_id)
        if user_id is not None:
            self.ensure_user(user_id, clinic_id=clinic_id)
        record = AuditLog(
            user_id=user_id,
            session_id=session_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            source=source,
            metadata_json=metadata_json,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def latest_session(self, session_id: str, *, clinic_id: Optional[str] = None) -> Optional[Session]:
        stmt = select(Session).where(Session.id == session_id)
        if clinic_id is not None:
            stmt = stmt.where(Session.clinic_id == clinic_id)
        return self.db.scalar(stmt)

    def save_review_snapshot(self, session_id: str, snapshot: dict, *, clinic_id: str) -> None:
        record = self._require_session_in_clinic(session_id, clinic_id)
        record.review_snapshot_json = snapshot
        self.db.flush()

    def get_review_snapshot(self, session_id: str, *, clinic_id: str) -> Optional[dict]:
        record = self.latest_session(session_id, clinic_id=clinic_id)
        if record is None or record.review_snapshot_json is None:
            return None
        return record.review_snapshot_json

    def get_session(self, session_id: str, *, clinic_id: str) -> Optional[dict]:
        record = self.latest_session(session_id, clinic_id=clinic_id)
        if record is None:
            return None
        return {
            "id": record.id,
            "clinic_id": record.clinic_id,
            "patient_id": record.patient_id,
            "dentist_id": record.dentist_id,
            "status": record.status,
            "session_type": record.session_type,
            "current_stage": record.current_stage,
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
            "clinical_notes": [
                {
                    "id": note.id,
                    "status": note.status,
                    "draft_json": note.draft_json,
                    "approved_json": note.approved_json,
                    "model_version": note.model_version,
                    "created_at": note.created_at.isoformat(),
                }
                for note in record.clinical_notes
            ],
            "transcripts": [
                {
                    "id": transcript.id,
                    "source": transcript.source,
                    "utterances_json": transcript.utterances_json,
                    "created_at": transcript.created_at.isoformat(),
                }
                for transcript in record.transcripts
            ],
            "code_suggestions": [
                {
                    "id": suggestion.id,
                    "code": suggestion.procedure_code.code if suggestion.procedure_code else None,
                    "match_state": suggestion.match_state,
                    "explanation": suggestion.explanation,
                    "accepted_by_user": suggestion.accepted_by_user,
                }
                for suggestion in record.code_suggestions
            ],
            "audit_logs": [
                {
                    "id": audit.id,
                    "user_id": audit.user_id,
                    "action": audit.action,
                    "entity_type": audit.entity_type,
                    "entity_id": audit.entity_id,
                    "source": audit.source,
                    "timestamp": audit.timestamp.isoformat(),
                    "metadata_json": audit.metadata_json,
                }
                for audit in record.audit_logs
            ],
        }

    def list_patients(self, *, clinic_id: str, query: Optional[str] = None) -> list[dict]:
        stmt = select(Patient).where(Patient.clinic_id == clinic_id)
        if query:
            like = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    Patient.display_name.ilike(like),
                    Patient.initials.ilike(like),
                    Patient.external_id.ilike(like),
                )
            )
        patients = list(self.db.scalars(stmt))
        return [self._patient_summary(patient) for patient in patients]

    def get_patient_sessions(self, patient_id: str, *, clinic_id: str) -> Optional[dict]:
        patient = self.db.scalar(
            select(Patient).where(Patient.id == patient_id, Patient.clinic_id == clinic_id)
        )
        if patient is None:
            return None
        sessions = sorted(patient.sessions, key=lambda record: record.started_at, reverse=True)
        return {
            "id": patient.id,
            "initials": patient.initials,
            "display_name": patient.display_name,
            "external_id": patient.external_id,
            "national_id": patient.national_id,
            "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
            "occupation": patient.occupation,
            "address": patient.address,
            "phone": patient.phone,
            "email": patient.email,
            "referred_by": patient.referred_by,
            "created_at": patient.created_at.isoformat(),
            "sessions": [self._session_summary(session) for session in sessions],
        }

    def find_user_by_email(self, email: str) -> Optional[User]:
        return self.db.scalar(select(User).where(User.email == email))

    def _patient_summary(self, patient: Patient) -> dict:
        sessions = sorted(patient.sessions, key=lambda record: record.started_at, reverse=True)
        latest = sessions[0] if sessions else None
        return {
            "id": patient.id,
            "initials": patient.initials,
            "display_name": patient.display_name,
            "external_id": patient.external_id,
            "national_id": patient.national_id,
            "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
            "occupation": patient.occupation,
            "address": patient.address,
            "phone": patient.phone,
            "email": patient.email,
            "referred_by": patient.referred_by,
            "created_at": patient.created_at.isoformat(),
            "last_session_at": latest.started_at.isoformat() if latest is not None else None,
            "session_count": len(sessions),
            "last_procedures": self._procedure_labels(latest) if latest is not None else [],
            "status": latest.status if latest is not None else "no_sessions",
        }

    def _session_summary(self, session: Session) -> dict:
        return {
            "id": session.id,
            "status": session.status,
            "session_type": session.session_type,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "completed_at": session.completed_at.isoformat() if session.completed_at else None,
            "procedures": self._procedure_labels(session),
        }

    def _require_patient_in_clinic(self, patient_id: str, clinic_id: str) -> Patient:
        patient = self.db.scalar(
            select(Patient).where(Patient.id == patient_id, Patient.clinic_id == clinic_id)
        )
        if patient is None:
            raise PermissionError("Hasta bulunamadı veya farklı kliniğe ait.")
        return patient

    def _procedure_labels(self, session: Session) -> list[str]:
        labels: list[str] = []
        for suggestion in session.code_suggestions:
            if suggestion.procedure_code is None:
                continue
            label = suggestion.procedure_code.title or suggestion.procedure_code.category
            if label and label not in labels:
                labels.append(label)
        return labels

    def _upsert_procedure_code(
        self,
        *,
        code: str,
        title: str,
        category: str,
        source_year: str,
    ) -> ProcedureCode:
        record = self.db.scalar(select(ProcedureCode).where(ProcedureCode.code == code))
        if record is None:
            record = ProcedureCode(
                code=code,
                title=title,
                category=category,
                source_year=source_year,
            )
            self.db.add(record)
            self.db.flush()
        return record

    def _mark_accepted_codes(self, session_id: str, selected_codes: list[str], *, clinic_id: str) -> None:
        self._require_session_in_clinic(session_id, clinic_id)
        stmt = (
            select(CodeSuggestion)
            .join(ProcedureCode, CodeSuggestion.procedure_code_id == ProcedureCode.id)
            .where(CodeSuggestion.session_id == session_id, ProcedureCode.code.in_(selected_codes))
        )
        for suggestion in self.db.scalars(stmt):
            suggestion.accepted_by_user = True

    def _require_session_in_clinic(self, session_id: str, clinic_id: str) -> Session:
        record = self.latest_session(session_id, clinic_id=clinic_id)
        if record is None:
            raise KeyError(session_id)
        return record


def _session_status(status: str) -> str:
    if status in (PipelineStatus.APPROVED.value, "approved"):
        return "approved"
    if status in (PipelineStatus.EXPORTED.value, "exported"):
        return "exported"
    return "draft"
