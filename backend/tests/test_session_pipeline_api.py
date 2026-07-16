from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth import hash_password
from app.api.main import app
from app.api.routes import get_llm_provider, get_session_repository
from app.api.session_pipeline import (
    ApproveReviewRequest,
    ManualFindingRequest,
    RoleCorrectionIn,
    TranscriptAnalyzeRequest,
    TranscriptResumeAfterRoleReviewRequest,
    TranscriptUtteranceIn,
    approve_review,
    add_manual_finding_to_session,
    analyze_transcript,
    create_session_from_transcript,
    resume_transcript_after_role_review,
    to_review_response,
)
from app.pipeline.types import (
    ClinicalNoteDraft,
    CodeSuggestionBundle,
    DentistRole,
    NoteSentence,
    PipelineResult,
    PipelineStatus,
    ProcedureObject,
    ProcedureStatus,
)
from app.providers.audio_processing import (
    AudioProviderConfigurationError,
    AudioProviderRuntimeError,
    DevFixtureAudioProcessingProvider,
    NotConfiguredAudioProcessingProvider,
    create_audio_processing_provider,
)
from app.providers.gemini_audio_provider import (
    GeminiAudioProcessingProvider,
    normalize_gemini_audio_response,
)
from app.providers.deepgram_audio_provider import (
    DeepgramAudioProcessingProvider,
    normalize_deepgram_audio_response,
)
from app.providers.managed_audio_provider import (
    ManagedHttpAudioProcessingProvider,
    normalize_managed_audio_response,
)
from app.providers.llm import LLMProvider


AUTH_HEADERS = {
    "X-Tandela-Clinic-Id": "clinic-test",
    "X-Tandela-User-Id": "doctor-header",
    "X-Tandela-User-Role": "dentist",
}


class ScriptedLLM(LLMProvider):
    def __init__(self, outputs: list[dict] | list[str]) -> None:
        self.outputs = list(outputs)

    def complete(self, system_prompt: str, user_input: str) -> str:
        if not self.outputs:
            raise AssertionError("ScriptedLLM output kalmadı")
        output = self.outputs.pop(0)
        if isinstance(output, str):
            return output
        return json.dumps(output, ensure_ascii=False)


class PerioScriptedLLM(LLMProvider):
    def complete(self, system_prompt: str, user_input: str) -> str:
        if "tooth_segments" in system_prompt:
            output = {
                "tooth_segments": [
                    {
                        "tooth_number_fdi": 16,
                        "source_quote": "16 bukkal üç dört dört, mobilite bir, furkasyon iki bukkal.",
                        "is_uncertain": False,
                        "sites": [
                            {"site": "MB", "pocket_depth_mm": 3},
                            {"site": "B", "pocket_depth_mm": 4},
                            {"site": "DB", "pocket_depth_mm": 4},
                        ],
                    }
                ],
                "unassigned_segments": [],
                "uncertain_items": [],
            }
        else:
            output = {
                "summaries": [
                    {
                        "tooth_number_fdi": 16,
                        "mobility_grade": 1,
                        "furcation_grade": 2,
                        "furcation_site": "buccal",
                        "source_quote": "16 bukkal üç dört dört, mobilite bir, furkasyon iki bukkal.",
                        "is_uncertain": False,
                    }
                ],
                "uncertain_items": [],
            }
        return json.dumps(output, ensure_ascii=False)


class SessionPipelineApiTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_perio_endpoint_runs_parallel_extractions_and_audits_separate_session(self) -> None:
        calls: list[tuple[str, dict]] = []

        class StubRepository:
            def latest_session(self, session_id: str, **kwargs):
                return None

            def upsert_session(self, session_id: str, **kwargs):
                calls.append(("upsert_session", {"session_id": session_id, **kwargs}))

            def save_transcript(self, session_id: str, utterances: list[dict], **kwargs):
                calls.append(
                    (
                        "save_transcript",
                        {"session_id": session_id, "utterances": utterances, **kwargs},
                    )
                )

            def add_audit_log(self, **kwargs):
                calls.append(("add_audit_log", kwargs))

            def save_review_snapshot(self, session_id: str, snapshot: dict, **kwargs):
                calls.append(
                    (
                        "save_review_snapshot",
                        {"session_id": session_id, "snapshot": snapshot, **kwargs},
                    )
                )

        app.dependency_overrides[get_llm_provider] = lambda: PerioScriptedLLM()
        app.dependency_overrides[get_session_repository] = lambda: StubRepository()
        client = TestClient(app)

        response = client.post(
            "/sessions/perio-integration/perio",
            headers=AUTH_HEADERS,
            json={
                "patient_id": "patient-perio",
                "dictation": "16 bukkal üç dört dört, mobilite bir, furkasyon iki bukkal."
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["measurements"]), 6)
        self.assertEqual(payload["measurements"][0]["tooth_number_fdi"], 16)
        self.assertEqual(len(payload["tooth_summaries"]), 1)
        self.assertEqual(payload["tooth_summaries"][0]["mobility_grade"], 1)
        self.assertEqual(payload["tooth_summaries"][0]["furcation_grade"], 2)
        self.assertEqual(payload["uncertain_items"], [])

        upsert = next(
            data
            for name, data in calls
            if name == "upsert_session" and data.get("current_stage") == "perio_review"
        )
        self.assertEqual(upsert["session_id"], "perio-integration")
        self.assertEqual(upsert["patient_id"], "patient-perio")
        self.assertEqual(upsert["session_type"], "perio")
        self.assertEqual(upsert["current_stage"], "perio_review")
        transcript = next(data for name, data in calls if name == "save_transcript")
        self.assertEqual(transcript["source"], "perio_dictation")
        audit = next(data for name, data in calls if name == "add_audit_log")
        self.assertEqual(audit["action"], "perio_extracted")
        self.assertEqual(audit["source"], "ai")
        self.assertNotIn("dictation", audit["metadata_json"])
        snapshot = next(data for name, data in calls if name == "save_review_snapshot")
        self.assertEqual(snapshot["snapshot"]["session_type"], "perio")
        self.assertEqual(snapshot["snapshot"]["perio_result"]["tooth_summaries"][0]["mobility_grade"], 1)

    def test_review_endpoint_returns_persisted_snapshot(self) -> None:
        snapshot = {
            "snapshot_version": 1,
            "session_id": "persisted-review",
            "session_type": "perio",
            "transcript": [{"speaker_id": "dentist", "text": "16 bukkal üç dört dört."}],
            "clinical_review": None,
            "clinical_pipeline": None,
            "perio_result": {"measurements": [], "tooth_summaries": [], "uncertain_items": []},
        }

        class StubRepository:
            def get_review_snapshot(self, session_id: str, **kwargs):
                return snapshot if session_id == "persisted-review" else None

        app.dependency_overrides[get_session_repository] = lambda: StubRepository()
        client = TestClient(app)

        response = client.get("/sessions/persisted-review/review", headers=AUTH_HEADERS)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), snapshot)

    def test_patient_creation_and_manual_session_attachment(self) -> None:
        calls: list[tuple[str, dict]] = []
        patient = SimpleNamespace(
            id="patient-created",
            initials=None,
            display_name="Ayşe Yılmaz",
            external_id="DOSYA-42",
            national_id=None,
            date_of_birth=None,
            occupation=None,
            address=None,
            phone=None,
            email=None,
            referred_by=None,
            created_at=datetime.now(timezone.utc),
        )

        class StubRepository:
            def create_patient(self, patient_id: str, **kwargs):
                calls.append(("create_patient", {"patient_id": patient_id, **kwargs}))
                return patient

            def attach_patient_to_session(self, session_id: str, patient_id: str, **kwargs):
                calls.append(("attach_patient", {"session_id": session_id, "patient_id": patient_id, **kwargs}))

            def add_audit_log(self, **kwargs):
                calls.append(("add_audit_log", kwargs))

        app.dependency_overrides[get_session_repository] = lambda: StubRepository()
        client = TestClient(app)

        empty = client.post("/patients", headers=AUTH_HEADERS, json={})
        self.assertEqual(empty.status_code, 400)

        created = client.post(
            "/patients",
            headers=AUTH_HEADERS,
            json={"display_name": " Ayşe Yılmaz ", "external_id": " DOSYA-42 "},
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["display_name"], "Ayşe Yılmaz")
        create_call = next(data for name, data in calls if name == "create_patient")
        self.assertEqual(create_call["clinic_id"], "clinic-test")
        self.assertEqual(create_call["display_name"], "Ayşe Yılmaz")
        self.assertEqual(create_call["external_id"], "DOSYA-42")

        attached = client.patch(
            "/sessions/session-patient-link/patient",
            headers=AUTH_HEADERS,
            json={"patient_id": "patient-created"},
        )
        self.assertEqual(attached.status_code, 200)
        self.assertEqual(attached.json()["patient_id"], "patient-created")
        audit = next(data for name, data in calls if name == "add_audit_log")
        self.assertEqual(audit["action"], "patient_attached")
        self.assertEqual(audit["source"], "manual")

    def test_perio_approve_persists_audit_and_guards_export_until_approved(self) -> None:
        snapshot = {
            "snapshot_version": 1,
            "session_id": "perio-approve-test",
            "session_type": "perio",
            "transcript": [],
            "clinical_review": None,
            "clinical_pipeline": None,
            "perio_result": {
                "measurements": [
                    {
                        "tooth_number_fdi": 16,
                        "site": "DB",
                        "pocket_depth_mm": 3,
                        "gingival_margin_mm": 0,
                        "bleeding_on_probing": True,
                        "plaque": True,
                        "recession_mm": None,
                        "source_quote": "16 bukkal üç dört dört.",
                        "is_uncertain": False,
                    },
                    {
                        "tooth_number_fdi": 16,
                        "site": "B",
                        "pocket_depth_mm": 4,
                        "gingival_margin_mm": -2,
                        "bleeding_on_probing": True,
                        "plaque": True,
                        "recession_mm": 2,
                        "source_quote": "16 bukkal üç dört dört.",
                        "is_uncertain": False,
                    },
                    {
                        "tooth_number_fdi": 16,
                        "site": "MB",
                        "pocket_depth_mm": 4,
                        "gingival_margin_mm": 0,
                        "bleeding_on_probing": True,
                        "plaque": True,
                        "recession_mm": None,
                        "source_quote": "16 bukkal üç dört dört.",
                        "is_uncertain": False,
                    },
                ],
                "tooth_summaries": [
                    {
                        "tooth_number_fdi": 16,
                        "mobility_grade": 1,
                        "furcation_grade": 2,
                        "furcation_site": "buccal",
                    }
                ],
                "uncertain_items": [],
            },
        }
        session = SimpleNamespace(
            id="perio-approve-test",
            clinic_id="clinic-test",
            patient_id="patient-perio",
            session_type="perio",
            status="draft",
        )
        calls: list[tuple[str, dict]] = []

        class StubRepository:
            def latest_session(self, session_id: str, **kwargs):
                return session if session_id == session.id else None

            def get_review_snapshot(self, session_id: str, **kwargs):
                return snapshot if session_id == session.id else None

            def upsert_session(self, session_id: str, **kwargs):
                session.status = kwargs["status"]
                calls.append(("upsert_session", {"session_id": session_id, **kwargs}))

            def add_audit_log(self, **kwargs):
                calls.append(("add_audit_log", kwargs))

            def save_review_snapshot(self, session_id: str, next_snapshot: dict, **kwargs):
                if next_snapshot is not snapshot:
                    snapshot.clear()
                    snapshot.update(next_snapshot)
                calls.append(("save_review_snapshot", {"session_id": session_id, **kwargs}))

        app.dependency_overrides[get_session_repository] = lambda: StubRepository()
        client = TestClient(app)

        blocked = client.get(
            "/sessions/perio-approve-test/perio/export", headers=AUTH_HEADERS
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("onaylanmadan export edilemez", blocked.json()["detail"])

        approved = client.post(
            "/sessions/perio-approve-test/perio/approve", headers=AUTH_HEADERS
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"], "approved")
        export_text = approved.json()["export_payload"]["perio_text"]
        self.assertIn("FDI 16: Cep: DB=3mm B=4mm MB=4mm", export_text)
        self.assertIn("Attachment: DB=3mm B=6mm MB=4mm", export_text)
        self.assertIn("Mobilite: 1; Furkasyon: 2 (buccal)", export_text)

        audit = next(data for name, data in calls if name == "add_audit_log")
        self.assertEqual(audit["action"], "perio_approved")
        self.assertEqual(audit["source"], "dentist")
        self.assertEqual(session.status, "approved")

        exported = client.get(
            "/sessions/perio-approve-test/perio/export", headers=AUTH_HEADERS
        )
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.json()["perio_text"], export_text)

        repeated = client.post(
            "/sessions/perio-approve-test/perio/approve", headers=AUTH_HEADERS
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(
            len([name for name, _ in calls if name == "add_audit_log"]),
            1,
        )

    def test_analyze_transcript_marks_role_review_but_continues_to_draft(self) -> None:
        request = TranscriptAnalyzeRequest(
            session_id="api-gate",
            utterances=[
                TranscriptUtteranceIn(speaker_id="A", text="Şikayetiniz nedir?"),
            ],
        )
        llm = ScriptedLLM(
            [
                {
                    "assignments": [
                        {
                            "speaker_id": "A",
                            "role": "dentist",
                            "status": "clear",
                            "utterance_count": 1,
                            "reason": "Tek cümle.",
                        }
                    ],
                    "manual_review_required": False,
                }
            ]
        )

        result = analyze_transcript(request, llm)

        self.assertEqual(result.status, PipelineStatus.AWAITING_DENTIST_REVIEW)
        self.assertEqual(result.stopped_at_stage, "dentist_review")
        self.assertIsNotNone(result.role_assignment)
        self.assertIsNotNone(result.clinical_facts)
        self.assertIsNotNone(result.clinical_note)
        self.assertEqual(result.procedures, [])
        self.assertEqual(result.code_suggestions, [])

        response = to_review_response(result)
        self.assertEqual(response.next_action, "review_note_and_codes")
        self.assertTrue(response.role_review_required)
        self.assertIsNotNone(response.role_review)
        self.assertIsNotNone(response.dentist_review)
        self.assertEqual(response.role_review.speakers[0].speaker_id, "A")
        self.assertEqual(response.uncertain_speakers[0].speaker_id, "A")

    def test_analyze_route_returns_review_dto_without_internal_pipeline_fields(self) -> None:
        app.dependency_overrides[get_llm_provider] = lambda: ScriptedLLM(
            [
                {
                    "assignments": [
                        {
                            "speaker_id": "A",
                            "role": "dentist",
                            "status": "clear",
                            "utterance_count": 1,
                            "reason": "Tek cümle.",
                        }
                    ],
                    "manual_review_required": False,
                }
            ]
        )
        client = TestClient(app)

        response = client.post(
            "/sessions/transcripts/analyze",
            json={
                "session_id": "api-route-gate",
                "utterances": [{"speaker_id": "A", "text": "Şikayetiniz nedir?"}],
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["next_action"], "review_note_and_codes")
        self.assertTrue(payload["role_review_required"])
        self.assertIn("role_review", payload)
        self.assertIn("dentist_review", payload)
        self.assertNotIn("speaker_labelled_transcript", payload)
        self.assertNotIn("clinical_facts", payload)

    def test_phase_b_session_endpoints_run_gate_resume_and_approve(self) -> None:
        llm = ScriptedLLM(
            [
                {
                    "assignments": [
                        {
                            "speaker_id": "A",
                            "role": "dentist",
                            "status": "clear",
                            "utterance_count": 2,
                            "reason": "Hekim gibi konuşuyor.",
                        },
                        {
                            "speaker_id": "B",
                            "role": "patient",
                            "status": "clear",
                            "utterance_count": 1,
                            "reason": "Hasta şikayeti.",
                        },
                        {
                            "speaker_id": "C",
                            "role": "assistant_or_other",
                            "status": "review_needed",
                            "utterance_count": 1,
                            "reason": "Tek ifade.",
                        },
                    ],
                    "manual_review_required": True,
                },
                {
                    "facts": [
                        {
                            "category": "clinical_findings",
                            "text": "46 numarada derin çürük görüyorum.",
                            "source_quote": "46 numarada derin çürük görüyorum",
                            "source_role": "dentist",
                            "source_speaker": "A",
                            "tooth_number_fdi": 46,
                            "status": None,
                            "is_uncertain": False,
                        },
                        {
                            "category": "procedures",
                            "text": "46 numara için kanal tedavisi planlandı.",
                            "source_quote": "46 numara için kanal tedavisi planlandı",
                            "source_role": "dentist",
                            "source_speaker": "A",
                            "tooth_number_fdi": 46,
                            "status": "planned",
                            "is_uncertain": False,
                        },
                    ],
                    "uncertain_items": [],
                },
                {
                    "patient_complaint": [],
                    "history": [],
                    "clinical_findings": [
                        {
                            "sentence_id": "s0",
                            "text": "46 numarada derin çürük görüyorum.",
                            "source_role": "dentist",
                            "source_quote": "46 numarada derin çürük görüyorum",
                        }
                    ],
                    "assessment": [],
                    "treatment_plan": [],
                    "procedures_note": [
                        {
                            "sentence_id": "s1",
                            "text": "46 numara için kanal tedavisi planlandı.",
                            "source_role": "dentist",
                            "source_quote": "46 numara için kanal tedavisi planlandı",
                        }
                    ],
                    "uncertain_items": [],
                    "is_draft": True,
                },
                [
                    {
                        "tooth_fdi": 46,
                        "surfaces": None,
                        "condition": "rct",
                        "status": "planned",
                        "source_quote": "46 numara için kanal tedavisi planlandı",
                    }
                ],
                {
                    "explanations": [
                        {"code": "END330", "fit_reason": "46 daimi molar olduğu için aday.", "caveat": "Kanal sayısı dokümantasyon için kontrol edilmeli."},
                    ],
                    "ambiguity_note": None,
                    "dentist_must_choose": True,
                },
                {
                    "facts": [
                        {
                            "category": "clinical_findings",
                            "text": "46 numarada derin çürük görüyorum.",
                            "source_quote": "46 numarada derin çürük görüyorum",
                            "source_role": "dentist",
                            "source_speaker": "A",
                            "tooth_number_fdi": 46,
                            "status": None,
                            "is_uncertain": False,
                        },
                        {
                            "category": "procedures",
                            "text": "46 numara için kanal tedavisi planlandı.",
                            "source_quote": "46 numara için kanal tedavisi planlandı",
                            "source_role": "dentist",
                            "source_speaker": "A",
                            "tooth_number_fdi": 46,
                            "status": "planned",
                            "is_uncertain": False,
                        },
                    ],
                    "uncertain_items": [],
                },
                {
                    "patient_complaint": [],
                    "history": [],
                    "clinical_findings": [
                        {
                            "sentence_id": "s0",
                            "text": "46 numarada derin çürük görüyorum.",
                            "source_role": "dentist",
                            "source_quote": "46 numarada derin çürük görüyorum",
                        }
                    ],
                    "assessment": [],
                    "treatment_plan": [],
                    "procedures_note": [
                        {
                            "sentence_id": "s1",
                            "text": "46 numara için kanal tedavisi planlandı.",
                            "source_role": "dentist",
                            "source_quote": "46 numara için kanal tedavisi planlandı",
                        }
                    ],
                    "uncertain_items": [],
                    "is_draft": True,
                },
                [
                    {
                        "tooth_fdi": 46,
                        "surfaces": None,
                        "condition": "rct",
                        "status": "planned",
                        "source_quote": "46 numara için kanal tedavisi planlandı",
                    }
                ],
                {
                    "explanations": [
                        {"code": "END330", "fit_reason": "46 daimi molar olduğu için aday.", "caveat": "Kanal sayısı dokümantasyon için kontrol edilmeli."},
                    ],
                    "ambiguity_note": None,
                    "dentist_must_choose": True,
                },
            ]
        )
        app.dependency_overrides[get_llm_provider] = lambda: llm
        client = TestClient(app)

        create_response = client.post(
            "/sessions",
            headers=AUTH_HEADERS,
            json={
                "session_id": "phase-b-loop",
                "utterances": [
                    {"speaker_id": "A", "text": "46 numarada derin çürük görüyorum."},
                    {"speaker_id": "B", "text": "Ağrım var."},
                    {"speaker_id": "C", "text": "Röntgeni açıyorum."},
                    {"speaker_id": "A", "text": "46 numara için kanal tedavisi planlandı."},
                ],
            },
        )

        self.assertEqual(create_response.status_code, 200)
        create_payload = create_response.json()
        self.assertEqual(create_payload["review_state"], "draft_requires_dentist_approval")
        self.assertEqual(create_payload["next_action"], "review_note_and_codes")
        self.assertTrue(create_payload["role_review_required"])
        self.assertIsNotNone(create_payload["dentist_review"])
        self.assertEqual(create_payload["role_review"]["speakers"][2]["review_state"], "review_needed")

        resume_response = client.post(
            "/sessions/phase-b-loop/resume-role-review",
            headers=AUTH_HEADERS,
            json={
                "corrected_roles": [
                    {"speaker_id": "A", "role": "dentist", "status": "clear"},
                    {"speaker_id": "B", "role": "patient", "status": "clear"},
                    {"speaker_id": "C", "role": "assistant_or_other", "status": "clear"},
                ]
            },
        )

        self.assertEqual(resume_response.status_code, 200)
        resume_payload = resume_response.json()
        self.assertEqual(resume_payload["review_state"], "draft_requires_dentist_approval")
        self.assertEqual(resume_payload["next_action"], "review_note_and_codes")
        self.assertIsNotNone(resume_payload["dentist_review"])
        self.assertEqual(
            resume_payload["dentist_review"]["note"]["clinical_findings"][0]["source_quote"],
            "46 numarada derin çürük görüyorum",
        )

        approve_response = client.post(
            "/sessions/phase-b-loop/approve",
            headers=AUTH_HEADERS,
            json={"selected_codes": ["END330"], "approved": True},
        )

        self.assertEqual(approve_response.status_code, 200)
        approve_payload = approve_response.json()
        self.assertEqual(approve_payload["review_state"], "approved_ready_for_export")
        self.assertEqual(approve_payload["next_action"], "export")
        self.assertIn("46 numarada derin çürük görüyorum.", approve_payload["export_payload"]["clinical_note_text"])
        self.assertEqual(approve_payload["export_payload"]["selected_codes"], ["END330"])

    def test_resume_after_role_review_runs_to_dentist_review(self) -> None:
        request = TranscriptResumeAfterRoleReviewRequest(
            session_id="api-resume",
            utterances=[
                TranscriptUtteranceIn(
                    speaker_id="A",
                    text="46 numarada derin çürük görüyorum. 46 numara için kanal tedavisi planlandı.",
                )
            ],
            corrected_roles=[
                RoleCorrectionIn(speaker_id="A", role=DentistRole.DENTIST),
            ],
        )
        llm = ScriptedLLM(
            [
                {
                    "facts": [
                        {
                            "category": "clinical_findings",
                            "text": "46 numarada derin çürük görüyorum.",
                            "source_quote": "46 numarada derin çürük görüyorum",
                            "source_role": "dentist",
                            "source_speaker": "A",
                            "tooth_number_fdi": 46,
                            "status": None,
                            "is_uncertain": False,
                        },
                        {
                            "category": "procedures",
                            "text": "46 numara için kanal tedavisi planlandı.",
                            "source_quote": "46 numara için kanal tedavisi planlandı",
                            "source_role": "dentist",
                            "source_speaker": "A",
                            "tooth_number_fdi": 46,
                            "status": "planned",
                            "is_uncertain": False,
                        },
                    ],
                    "uncertain_items": [],
                },
                {
                    "patient_complaint": [],
                    "history": [],
                    "clinical_findings": [
                        {
                            "sentence_id": "s0",
                            "text": "46 numarada derin çürük görüyorum.",
                            "source_role": "dentist",
                            "source_quote": "46 numarada derin çürük görüyorum",
                        }
                    ],
                    "assessment": [],
                    "treatment_plan": [],
                    "procedures_note": [
                        {
                            "sentence_id": "s1",
                            "text": "46 numara için kanal tedavisi planlandı.",
                            "source_role": "dentist",
                            "source_quote": "46 numara için kanal tedavisi planlandı",
                        }
                    ],
                    "uncertain_items": [],
                    "is_draft": True,
                },
                [
                    {
                        "tooth_fdi": 46,
                        "surfaces": None,
                        "condition": "rct",
                        "status": "planned",
                        "source_quote": "46 numara için kanal tedavisi planlandı",
                    }
                ],
                {
                    "explanations": [
                        {"code": "END330", "fit_reason": "46 daimi molar olduğu için aday.", "caveat": "Kanal sayısı dokümantasyon için kontrol edilmeli."},
                    ],
                    "ambiguity_note": None,
                    "dentist_must_choose": True,
                },
            ]
        )

        result = resume_transcript_after_role_review(request, llm)

        self.assertEqual(result.status, PipelineStatus.AWAITING_DENTIST_REVIEW)
        self.assertEqual(result.stopped_at_stage, "dentist_review")
        self.assertIsNotNone(result.clinical_facts)
        self.assertIsNotNone(result.clinical_note)
        self.assertEqual(result.procedures[0].procedure_family, "kanal_tedavisi")
        self.assertEqual(len(result.code_suggestions[0].candidates), 1)
        self.assertEqual(len(result.code_suggestions[0].explanations), 1)

        response = to_review_response(result)
        self.assertEqual(response.next_action, "review_note_and_codes")
        self.assertIsNone(response.role_review)
        self.assertIsNotNone(response.dentist_review)
        self.assertEqual(len(response.dentist_review.procedures), 1)
        self.assertEqual(len(response.dentist_review.procedures[0].candidates), 1)

    def test_resume_after_role_review_marks_missing_speaker_but_continues_to_draft(self) -> None:
        request = TranscriptResumeAfterRoleReviewRequest(
            session_id="api-resume-missing-role",
            utterances=[
                TranscriptUtteranceIn(speaker_id="A", text="Muayene bulgusu."),
                TranscriptUtteranceIn(speaker_id="B", text="Ağrım var."),
            ],
            corrected_roles=[
                RoleCorrectionIn(speaker_id="A", role=DentistRole.DENTIST),
            ],
        )

        result = resume_transcript_after_role_review(request, ScriptedLLM([]))

        self.assertEqual(result.status, PipelineStatus.AWAITING_DENTIST_REVIEW)
        self.assertEqual(result.stopped_at_stage, "dentist_review")
        self.assertIsNotNone(result.clinical_facts)

        response = to_review_response(result)
        self.assertEqual(response.next_action, "review_note_and_codes")
        self.assertTrue(response.role_review_required)
        self.assertIsNotNone(response.role_review)

    def test_approve_review_moves_to_export_next_action(self) -> None:
        note = ClinicalNoteDraft(
            session_id="api-approve",
            clinical_findings=[
                NoteSentence(
                    sentence_id="s0",
                    text="46 numarada derin çürük görüyorum.",
                    source_role=DentistRole.DENTIST,
                    source_quote="46 numarada derin çürük görüyorum",
                )
            ],
            procedures_note=[
                NoteSentence(
                    sentence_id="s1",
                    text="46 numara için kanal tedavisi planlandı.",
                    source_role=DentistRole.DENTIST,
                    source_quote="46 numara için kanal tedavisi planlandı",
                )
            ],
        )
        result = approve_review(
            ApproveReviewRequest(
                session_id="api-approve",
                selected_codes=["END330"],
                reviewer_user_id="doctor-1",
                approved_note=note,
            )
        )

        self.assertEqual(result.status, PipelineStatus.APPROVED)
        self.assertEqual(result.stopped_at_stage, "ready_for_export")
        self.assertIsNotNone(result.review_decision)

        response = to_review_response(result)
        self.assertEqual(response.next_action, "export")
        self.assertIsNotNone(response.export_payload)
        self.assertIn("46 numarada derin çürük görüyorum.", response.export_payload.clinical_note_text)
        self.assertEqual(response.export_payload.selected_codes, ["END330"])
        self.assertEqual(response.export_payload.audit.reviewer_user_id, "doctor-1")

    def test_review_response_preserves_dynamic_tooth_number_for_frontend_chart(self) -> None:
        note = ClinicalNoteDraft(session_id="chart-44")
        result = PipelineResult(
            session_id="chart-44",
            status=PipelineStatus.AWAITING_DENTIST_REVIEW,
            clinical_note=note,
            procedures=[
                ProcedureObject(
                    procedure_family="kanal_tedavisi",
                    tooth_number_fdi=44,
                    status=ProcedureStatus.PLANNED,
                    source_quotes=["44 numara için kanal tedavisi planlandı"],
                )
            ],
            code_suggestions=[CodeSuggestionBundle(session_id="chart-44")],
            stopped_at_stage="dentist_review",
        )

        response = to_review_response(result)

        self.assertIsNotNone(response.dentist_review)
        self.assertEqual(response.dentist_review.procedures[0].procedure.tooth_number_fdi, 44)

    def test_add_manual_finding_appends_validated_procedure(self) -> None:
        request = TranscriptAnalyzeRequest(
            session_id="manual-finding",
            utterances=[
                TranscriptUtteranceIn(
                    speaker_id="A",
                    text="46 numara için kanal tedavisi planlandı.",
                )
            ],
        )
        llm = ScriptedLLM(
            [
                {
                    "assignments": [
                        {
                            "speaker_id": "A",
                            "role": "dentist",
                            "status": "clear",
                            "utterance_count": 1,
                            "reason": "Hekim.",
                        }
                    ],
                    "manual_review_required": False,
                },
                {
                    "facts": [],
                    "uncertain_items": [],
                },
                {
                    "patient_complaint": [],
                    "history": [],
                    "clinical_findings": [],
                    "assessment": [],
                    "treatment_plan": [],
                    "procedures_note": [],
                    "uncertain_items": [],
                    "is_draft": True,
                },
            ]
        )

        create_session_from_transcript(request, llm)
        result = add_manual_finding_to_session(
            "manual-finding",
            ManualFindingRequest(tooth_number_fdi=27, condition="caries", note="Manuel çürük bulgusu."),
        )

        self.assertEqual(result.status, PipelineStatus.AWAITING_DENTIST_REVIEW)
        self.assertEqual(result.procedures[-1].tooth_number_fdi, 27)
        self.assertEqual(result.procedures[-1].condition.value, "caries")
        self.assertTrue(result.procedures[-1].is_manual)
        self.assertEqual(result.procedures[-1].source_role, DentistRole.DENTIST)

    def test_add_manual_finding_rejects_invalid_fdi(self) -> None:
        request = TranscriptAnalyzeRequest(
            session_id="manual-finding-invalid",
            utterances=[
                TranscriptUtteranceIn(speaker_id="A", text="Not yok."),
            ],
        )
        llm = ScriptedLLM(
            [
                {
                    "assignments": [
                        {
                            "speaker_id": "A",
                            "role": "dentist",
                            "status": "clear",
                            "utterance_count": 1,
                            "reason": "Hekim.",
                        }
                    ],
                    "manual_review_required": False,
                },
                {"facts": [], "uncertain_items": []},
                {
                    "patient_complaint": [],
                    "history": [],
                    "clinical_findings": [],
                    "assessment": [],
                    "treatment_plan": [],
                    "procedures_note": [],
                    "uncertain_items": [],
                    "is_draft": True,
                },
            ]
        )

        create_session_from_transcript(request, llm)
        with self.assertRaises(ValueError):
            add_manual_finding_to_session(
                "manual-finding-invalid",
                ManualFindingRequest(tooth_number_fdi=20, condition="caries"),
            )

    def test_audio_process_route_deletes_raw_audio_when_provider_not_configured(self) -> None:
        client = TestClient(app)

        with patch.dict("os.environ", {"TANDELA_AUDIO_PROVIDER": "not_configured"}):
            response = client.post(
                "/sessions/audio/process",
                data={"session_id": "audio-skeleton"},
                files={"audio": ("sample.webm", b"not-real-audio", "audio/webm")},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "provider_not_configured")
        self.assertTrue(payload["raw_audio_deleted"])
        self.assertIsNone(payload["transcript"])

    def test_audio_process_route_returns_fixture_transcript_for_dev_provider(self) -> None:
        client = TestClient(app)

        with patch.dict("os.environ", {"TANDELA_AUDIO_PROVIDER": "dev_fixture"}):
            response = client.post(
                "/sessions/audio/process",
                data={"session_id": "audio-dev-fixture"},
                files={"audio": ("sample.webm", b"not-real-audio", "audio/webm")},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "transcript_ready")
        self.assertTrue(payload["raw_audio_deleted"])
        self.assertEqual(payload["transcript"]["session_id"], "audio-dev-fixture")
        self.assertGreaterEqual(len(payload["transcript"]["utterances"]), 3)
        self.assertEqual(payload["transcript"]["utterances"][0]["speaker_id"], "A")

    def test_audio_job_route_returns_status_and_result_for_dev_provider(self) -> None:
        client = TestClient(app)

        with patch.dict("os.environ", {"TANDELA_AUDIO_PROVIDER": "dev_fixture"}):
            response = client.post(
                "/sessions/audio/jobs",
                data={"session_id": "audio-job-fixture"},
                files={"audio": ("sample.webm", b"not-real-audio", "audio/webm")},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["session_id"], "audio-job-fixture")
        self.assertEqual(payload["status"], "done")
        self.assertIsNotNone(payload["result"])
        self.assertEqual(payload["result"]["status"], "transcript_ready")
        self.assertTrue(payload["result"]["raw_audio_deleted"])

        status_response = client.get(f"/sessions/audio/jobs/{payload['job_id']}")
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["job_id"], payload["job_id"])

    def test_session_audio_route_feeds_transcript_into_pipeline_and_deletes_raw_audio(self) -> None:
        app.dependency_overrides[get_llm_provider] = lambda: ScriptedLLM(
            [
                {
                    "assignments": [
                        {
                            "speaker_id": "A",
                            "role": "dentist",
                            "status": "clear",
                            "utterance_count": 4,
                            "reason": "Muayeneyi yönetiyor.",
                        },
                        {
                            "speaker_id": "B",
                            "role": "patient",
                            "status": "clear",
                            "utterance_count": 1,
                            "reason": "Şikayet bildiriyor.",
                        },
                        {
                            "speaker_id": "C",
                            "role": "assistant_or_other",
                            "status": "review_needed",
                            "utterance_count": 1,
                            "reason": "Tek ifade.",
                        },
                    ],
                    "manual_review_required": True,
                }
            ]
        )
        client = TestClient(app)

        with patch.dict("os.environ", {"TANDELA_AUDIO_PROVIDER": "dev_fixture"}):
            response = client.post(
                "/sessions/audio-phase-c/audio",
                headers=AUTH_HEADERS,
                files={"audio": ("sample.webm", b"not-real-audio", "audio/webm")},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["next_action"], "review_note_and_codes")
        self.assertTrue(payload["role_review_required"])
        self.assertEqual(payload["audio_processing"]["status"], "transcript_ready")
        self.assertTrue(payload["audio_processing"]["raw_audio_deleted"])
        self.assertEqual(payload["audio_processing"]["transcript"]["session_id"], "audio-phase-c")

    def test_audio_job_status_returns_404_for_unknown_job(self) -> None:
        client = TestClient(app)

        response = client.get("/sessions/audio/jobs/missing-job")

        self.assertEqual(response.status_code, 404)

    def test_approve_route_uses_auth_user_for_reviewer_identity(self) -> None:
        saved: dict = {}

        class StubRepository:
            def save_clinical_note(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
                saved["note_kwargs"] = kwargs

            def save_review_approval(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
                saved["review_kwargs"] = kwargs

        app.dependency_overrides[get_session_repository] = lambda: StubRepository()
        client = TestClient(app)
        note = ClinicalNoteDraft(
            session_id="auth-approve",
            clinical_findings=[
                NoteSentence(
                    sentence_id="s0",
                    text="46 numarada derin çürük görüyorum.",
                    source_role=DentistRole.DENTIST,
                    source_quote="46 numarada derin çürük görüyorum",
                )
            ],
        )

        response = client.post(
            "/sessions/reviews/approve",
            headers=AUTH_HEADERS,
            json={
                "session_id": "auth-approve",
                "selected_codes": ["END330"],
                "reviewer_user_id": "body-user-should-not-win",
                "approved": True,
                "approved_note": note.model_dump(mode="json"),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["export_payload"]["audit"]["reviewer_user_id"], "doctor-header")
        self.assertEqual(saved["review_kwargs"]["reviewer_user_id"], "doctor-header")
        self.assertEqual(saved["review_kwargs"]["clinic_id"], "clinic-test")
        self.assertEqual(saved["note_kwargs"]["actor_user_id"], "doctor-header")

    def test_required_auth_mode_rejects_missing_headers(self) -> None:
        client = TestClient(app)

        with patch.dict("os.environ", {"TANDELA_AUTH_MODE": "required"}):
            response = client.get("/sessions/audio/jobs/missing-job")

        self.assertEqual(response.status_code, 401)

    def test_login_returns_jwt_and_sessions_accept_bearer_token(self) -> None:
        class StubRepository:
            def find_user_by_email(self, email):  # noqa: ANN001, ANN201
                if email != "dentist@test.tandela":
                    return None
                return SimpleNamespace(
                    id="doctor-jwt",
                    clinic_id="clinic-jwt",
                    role="dentist",
                    password_hash=hash_password("secret-pass"),
                )

        app.dependency_overrides[get_session_repository] = lambda: StubRepository()
        client = TestClient(app)

        with patch.dict("os.environ", {"TANDELA_AUTH_MODE": "jwt", "SECRET_KEY": "test-secret"}):
            login = client.post(
                "/auth/login",
                json={"email": "dentist@test.tandela", "password": "secret-pass"},
            )
            self.assertEqual(login.status_code, 200)
            token = login.json()["access_token"]

            authed = client.get(
                "/sessions/audio/jobs/missing-job",
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(authed.status_code, 404)

    def test_audio_provider_factory_defaults_to_safe_not_configured_provider(self) -> None:
        with patch.dict("os.environ", {"TANDELA_AUDIO_PROVIDER": "not_configured"}):
            provider = create_audio_processing_provider()

        self.assertIsInstance(provider, NotConfiguredAudioProcessingProvider)

    def test_audio_provider_factory_supports_dev_fixture_provider(self) -> None:
        provider = create_audio_processing_provider("dev_fixture")

        self.assertIsInstance(provider, DevFixtureAudioProcessingProvider)

    def test_audio_provider_factory_supports_managed_http_provider_with_env(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "TANDELA_AUDIO_ENDPOINT_URL": "https://audio.example.invalid/process",
                "TANDELA_AUDIO_API_KEY": "test-key",
                "TANDELA_AUDIO_REGION": "eu",
            },
            clear=True,
        ):
            provider = create_audio_processing_provider("managed_http")

        self.assertIsInstance(provider, ManagedHttpAudioProcessingProvider)

    def test_audio_provider_factory_supports_gemini_audio_with_env(self) -> None:
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            provider = create_audio_processing_provider("gemini_audio")

        self.assertIsInstance(provider, GeminiAudioProcessingProvider)

    def test_audio_provider_factory_supports_deepgram_with_eu_endpoint(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "DEEPGRAM_API_KEY": "test-key",
                "DEEPGRAM_BASE_URL": "https://api.eu.deepgram.com",
            },
            clear=True,
        ):
            provider = create_audio_processing_provider("deepgram")

        self.assertIsInstance(provider, DeepgramAudioProcessingProvider)

    def test_audio_provider_factory_rejects_deepgram_non_eu_endpoint(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "DEEPGRAM_API_KEY": "test-key",
                "DEEPGRAM_BASE_URL": "https://api.deepgram.com",
            },
            clear=True,
        ):
            with self.assertRaises(AudioProviderConfigurationError):
                create_audio_processing_provider("deepgram")

    def test_audio_provider_factory_rejects_managed_http_without_required_env(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(AudioProviderConfigurationError):
                create_audio_processing_provider("managed_http")

    def test_audio_provider_factory_rejects_non_compliant_audio_region(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "TANDELA_AUDIO_ENDPOINT_URL": "https://audio.example.invalid/process",
                "TANDELA_AUDIO_API_KEY": "test-key",
                "TANDELA_AUDIO_REGION": "us",
            },
            clear=True,
        ):
            with self.assertRaises(AudioProviderConfigurationError):
                create_audio_processing_provider("managed_http")

    def test_managed_audio_response_normalizes_to_speaker_labelled_transcript(self) -> None:
        transcript = normalize_managed_audio_response(
            "managed-normalize",
            {
                "session_id": "vendor-session",
                "language": "tr",
                "utterances": [
                    {
                        "speaker_id": " A ",
                        "text": "Merhaba, şikayetiniz nedir?",
                        "start_sec": 0,
                        "end_sec": 1.5,
                        "words": [
                            {"text": "Merhaba,", "start_sec": 0, "end_sec": 0.3},
                            {"text": "şikayetiniz", "start_sec": 0.35, "end_sec": 0.7},
                        ],
                    }
                ],
            },
        )

        self.assertEqual(transcript.session_id, "managed-normalize")
        self.assertEqual(transcript.utterances[0].speaker_id, "A")
        self.assertEqual(transcript.utterances[0].words[0].text, "Merhaba,")

    def test_managed_audio_response_rejects_empty_transcript(self) -> None:
        with self.assertRaises(AudioProviderRuntimeError):
            normalize_managed_audio_response("managed-empty", {"utterances": []})

    def test_gemini_audio_response_normalizes_without_timestamps(self) -> None:
        transcript = normalize_gemini_audio_response(
            "gemini-audio-normalize",
            {
                "utterances": [
                    {"speaker_id": "a", "text": "46 numarada derin çürük görüyorum."},
                    {"speaker_id": "b", "text": "Sağ alt tarafta ağrım var."},
                ]
            },
        )

        self.assertEqual(transcript.session_id, "gemini-audio-normalize")
        self.assertEqual(transcript.utterances[0].speaker_id, "A")
        self.assertEqual(transcript.utterances[1].speaker_id, "B")
        self.assertGreater(transcript.utterances[0].end_sec, transcript.utterances[0].start_sec)
        self.assertGreater(len(transcript.utterances[0].words), 0)

    def test_deepgram_response_normalizes_utterances_to_speaker_labelled_transcript(self) -> None:
        transcript = normalize_deepgram_audio_response(
            "deepgram-normalize",
            {
                "results": {
                    "utterances": [
                        {
                            "speaker": 0,
                            "start": 0.0,
                            "end": 1.4,
                            "transcript": "Merhaba, şikayetiniz nedir?",
                            "words": [
                                {"word": "merhaba", "punctuated_word": "Merhaba,", "start": 0.0, "end": 0.4, "speaker": 0},
                                {"word": "şikayetiniz", "punctuated_word": "şikayetiniz", "start": 0.5, "end": 0.9, "speaker": 0},
                            ],
                        },
                        {
                            "speaker": 1,
                            "start": 1.5,
                            "end": 3.0,
                            "transcript": "Sağ alt tarafta ağrım var.",
                            "words": [],
                        },
                    ],
                    "channels": [],
                }
            },
        )

        self.assertEqual(transcript.session_id, "deepgram-normalize")
        self.assertEqual(transcript.utterances[0].speaker_id, "A")
        self.assertEqual(transcript.utterances[1].speaker_id, "B")
        self.assertEqual(transcript.utterances[0].words[0].text, "Merhaba,")

    def test_audio_provider_factory_rejects_unknown_provider(self) -> None:
        with self.assertRaises(AudioProviderConfigurationError):
            create_audio_processing_provider("unknown-vendor")


if __name__ == "__main__":
    unittest.main()
