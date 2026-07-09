from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import select

from app.api.session_pipeline import ExportAuditOut, ExportPayloadOut
from app.models.database import create_database_engine, create_session_factory, init_database
from app.models.session_records import (
    AuditLog,
    ClinicalNote,
    CodeSuggestion,
    Session,
    Transcript,
)
from app.pipeline.types import CandidateCode, ClinicalNoteDraft, CodeSuggestionBundle, DentistRole, NoteSentence
from app.repositories.session_repository import SessionRepository


class SessionRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "repo-test.db"
        self.engine = create_database_engine(f"sqlite:///{db_path}")
        init_database(self.engine)
        self.session_factory = create_session_factory(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmpdir.cleanup()

    def test_repository_persists_session_transcript_note_review_export_and_audit(self) -> None:
        db = self.session_factory()
        try:
            repo = SessionRepository(db)
            note = ClinicalNoteDraft(
                session_id="persist-s1",
                clinical_findings=[
                    NoteSentence(
                        sentence_id="s0",
                        text="46 numarada derin çürük görüyorum.",
                        source_role=DentistRole.DENTIST,
                        source_quote="46 numarada derin çürük görüyorum",
                    )
                ],
            )
            export = ExportPayloadOut(
                session_id="persist-s1",
                clinical_note_text="Klinik bulgular\n- 46 numarada derin çürük görüyorum.",
                selected_codes=["FIX-KANAL-2K"],
                audit=ExportAuditOut(
                    reviewer_user_id="doctor-1",
                    approved=True,
                    created_at_utc="2026-06-28T00:00:00+00:00",
                ),
            )

            repo.save_transcript(
                "persist-s1",
                [{"speaker_id": "A", "text": "46 numarada derin çürük görüyorum."}],
                source="test",
                clinic_id="clinic-1",
                actor_user_id="doctor-1",
            )
            repo.save_clinical_note("persist-s1", note, clinic_id="clinic-1", actor_user_id="doctor-1")
            repo.save_review_approval(
                "persist-s1",
                approved=True,
                selected_codes=["FIX-KANAL-2K"],
                reviewer_user_id="doctor-1",
                export_payload=export,
                clinic_id="clinic-1",
            )
            db.commit()

            session = db.get(Session, "persist-s1")
            self.assertIsNotNone(session)
            self.assertEqual(session.status, "approved")
            self.assertEqual(session.clinic_id, "clinic-1")
            self.assertEqual(db.scalar(select(Transcript).where(Transcript.session_id == "persist-s1")).source, "test")
            note_record = db.scalar(select(ClinicalNote).where(ClinicalNote.session_id == "persist-s1"))
            self.assertEqual(note_record.status, "draft")
            self.assertIn("clinical_findings", note_record.draft_json)
            audit_actions = [
                row.action
                for row in db.scalars(select(AuditLog).where(AuditLog.session_id == "persist-s1"))
            ]
            self.assertIn("transcript_saved", audit_actions)
            self.assertIn("clinical_note_saved", audit_actions)
            self.assertIn("doctor_review_approved", audit_actions)
            self.assertIn("export_payload_created", audit_actions)
            audit_actors = {
                row.user_id
                for row in db.scalars(select(AuditLog).where(AuditLog.session_id == "persist-s1"))
            }
            self.assertIn("doctor-1", audit_actors)
            export_audit = db.scalar(
                select(AuditLog).where(
                    AuditLog.session_id == "persist-s1",
                    AuditLog.action == "export_payload_created",
                )
            )
            self.assertEqual(export_audit.metadata_json["selected_codes"], ["FIX-KANAL-2K"])
            self.assertIsNotNone(repo.get_session("persist-s1", clinic_id="clinic-1"))
            self.assertIsNone(repo.get_session("persist-s1", clinic_id="other-clinic"))
        finally:
            db.close()

    def test_reanalysis_replaces_active_note_and_code_suggestions_but_keeps_transcripts(self) -> None:
        db = self.session_factory()
        try:
            repo = SessionRepository(db)
            first_note = ClinicalNoteDraft(
                session_id="persist-reanalysis",
                clinical_findings=[
                    NoteSentence(
                        sentence_id="s0",
                        text="İlk taslak.",
                        source_role=DentistRole.DENTIST,
                        source_quote="İlk kaynak",
                    )
                ],
            )
            second_note = ClinicalNoteDraft(
                session_id="persist-reanalysis",
                clinical_findings=[
                    NoteSentence(
                        sentence_id="s0",
                        text="Güncel taslak.",
                        source_role=DentistRole.DENTIST,
                        source_quote="Güncel kaynak",
                    )
                ],
            )

            repo.save_transcript(
                "persist-reanalysis",
                [{"speaker_id": "A", "text": "İlk kaynak"}],
                source="manual_transcript",
                clinic_id="clinic-1",
                actor_user_id="doctor-1",
            )
            repo.save_clinical_note(
                "persist-reanalysis",
                first_note,
                clinic_id="clinic-1",
                actor_user_id="doctor-1",
            )
            repo.save_code_suggestions(
                "persist-reanalysis",
                [
                    CodeSuggestionBundle(
                        session_id="persist-reanalysis",
                        candidates=[
                            CandidateCode(
                                code="FIX-OLD",
                                procedure_name="Eski Kod",
                                category="Test",
                            )
                        ],
                    )
                ],
                clinic_id="clinic-1",
            )
            repo.save_transcript(
                "persist-reanalysis",
                [{"speaker_id": "A", "text": "Güncel kaynak"}],
                source="manual_transcript",
                clinic_id="clinic-1",
                actor_user_id="doctor-1",
            )
            repo.save_clinical_note(
                "persist-reanalysis",
                second_note,
                clinic_id="clinic-1",
                actor_user_id="doctor-1",
            )
            repo.save_code_suggestions(
                "persist-reanalysis",
                [
                    CodeSuggestionBundle(
                        session_id="persist-reanalysis",
                        candidates=[
                            CandidateCode(
                                code="FIX-NEW",
                                procedure_name="Güncel Kod",
                                category="Test",
                            )
                        ],
                    )
                ],
                clinic_id="clinic-1",
            )
            db.commit()

            notes = list(db.scalars(select(ClinicalNote).where(ClinicalNote.session_id == "persist-reanalysis")))
            transcripts = list(db.scalars(select(Transcript).where(Transcript.session_id == "persist-reanalysis")))
            suggestions = list(db.scalars(select(CodeSuggestion).where(CodeSuggestion.session_id == "persist-reanalysis")))
            audit_actions = [
                row.action
                for row in db.scalars(select(AuditLog).where(AuditLog.session_id == "persist-reanalysis"))
            ]

            self.assertEqual(len(notes), 1)
            self.assertEqual(notes[0].draft_json["clinical_findings"][0]["text"], "Güncel taslak.")
            self.assertEqual(len(transcripts), 2)
            self.assertEqual(len(suggestions), 1)
            self.assertEqual(suggestions[0].procedure_code.code, "FIX-NEW")
            self.assertIn("draft_replaced", audit_actions)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
