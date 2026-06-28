"""Repository for MVP session persistence."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.session_records import (
    AuditLogRecord,
    ClinicalNoteRecord,
    ExportPayloadRecord,
    ReviewDecisionRecord,
    SessionRecord,
    TranscriptRecord,
)
from app.pipeline.types import ClinicalNoteDraft


class SessionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert_session(
        self,
        session_id: str,
        *,
        status: str,
        current_stage: Optional[str] = None,
        clinic_id: Optional[str] = None,
        patient_ref: Optional[str] = None,
    ) -> SessionRecord:
        record = self.db.get(SessionRecord, session_id)
        if record is None:
            record = SessionRecord(
                id=session_id,
                clinic_id=clinic_id,
                patient_ref=patient_ref,
                status=status,
                current_stage=current_stage,
            )
            self.db.add(record)
        else:
            record.status = status
            record.current_stage = current_stage
            if clinic_id is not None:
                record.clinic_id = clinic_id
            if patient_ref is not None:
                record.patient_ref = patient_ref
        self.db.flush()
        return record

    def save_transcript(
        self,
        session_id: str,
        utterances: list[dict],
        *,
        source: str = "transcript",
        clinic_id: Optional[str] = None,
        actor_user_id: Optional[str] = None,
    ) -> TranscriptRecord:
        self.upsert_session(
            session_id,
            status="transcript_received",
            current_stage="transcript",
            clinic_id=clinic_id,
        )
        record = TranscriptRecord(
            session_id=session_id,
            source=source,
            utterances_json=utterances,
        )
        self.db.add(record)
        self._audit(
            session_id=session_id,
            action="transcript_saved",
            source=source,
            payload={"utterance_count": len(utterances)},
            actor_user_id=actor_user_id,
        )
        self.db.flush()
        return record

    def save_clinical_note(
        self,
        session_id: str,
        note: ClinicalNoteDraft,
        *,
        status: str = "draft",
        clinic_id: Optional[str] = None,
        actor_user_id: Optional[str] = None,
    ) -> ClinicalNoteRecord:
        self.upsert_session(
            session_id,
            status="awaiting_dentist_review",
            current_stage="dentist_review",
            clinic_id=clinic_id,
        )
        record = ClinicalNoteRecord(
            session_id=session_id,
            note_json=note.model_dump(mode="json"),
            note_text=_note_text(note),
            status=status,
        )
        self.db.add(record)
        self._audit(
            session_id=session_id,
            action="clinical_note_saved",
            source="ai",
            payload={"status": status},
            actor_user_id=actor_user_id,
        )
        self.db.flush()
        return record

    def save_review_approval(
        self,
        session_id: str,
        *,
        approved: bool,
        selected_codes: list[str],
        reviewer_user_id: Optional[str],
        export_payload: Optional[Any],
        clinic_id: Optional[str] = None,
    ) -> ReviewDecisionRecord:
        self.upsert_session(
            session_id,
            status="approved" if approved else "review_rejected",
            current_stage="ready_for_export" if approved else "dentist_review",
            clinic_id=clinic_id,
        )
        decision = ReviewDecisionRecord(
            session_id=session_id,
            reviewer_user_id=reviewer_user_id,
            approved=approved,
            selected_codes_json=selected_codes,
            decision_json={
                "approved": approved,
                "selected_codes": selected_codes,
                "reviewer_user_id": reviewer_user_id,
            },
        )
        self.db.add(decision)
        if export_payload is not None:
            self.db.add(
                ExportPayloadRecord(
                    session_id=session_id,
                    payload_json=export_payload.model_dump(mode="json"),
                )
            )
        self._audit(
            session_id=session_id,
            actor_user_id=reviewer_user_id,
            action="doctor_review_approved" if approved else "doctor_review_rejected",
            source="manual",
            payload={"selected_codes": selected_codes},
        )
        self.db.flush()
        return decision

    def latest_session(self, session_id: str) -> Optional[SessionRecord]:
        return self.db.scalar(select(SessionRecord).where(SessionRecord.id == session_id))

    def _audit(
        self,
        *,
        session_id: str,
        action: str,
        source: str,
        payload: dict,
        actor_user_id: Optional[str] = None,
    ) -> None:
        self.db.add(
            AuditLogRecord(
                session_id=session_id,
                actor_user_id=actor_user_id,
                action=action,
                source=source,
                payload_json=payload,
            )
        )


def _note_text(note: ClinicalNoteDraft) -> str:
    sections = [
        ("Hasta şikayeti", note.patient_complaint),
        ("Geçmiş", note.history),
        ("Klinik bulgular", note.clinical_findings),
        ("Değerlendirme", note.assessment),
        ("Tedavi planı", note.treatment_plan),
        ("İşlem notu", note.procedures_note),
    ]
    lines: list[str] = []
    for title, sentences in sections:
        if not sentences:
            continue
        lines.append(title)
        lines.extend(f"- {sentence.text}" for sentence in sentences)
        lines.append("")
    if note.uncertain_items:
        lines.append("Belirsiz / hekim review maddeleri")
        lines.extend(f"- {item}" for item in note.uncertain_items)
        lines.append("")
    return "\n".join(lines).strip()
