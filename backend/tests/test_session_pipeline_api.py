from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.main import app
from app.api.routes import get_llm_provider, get_session_repository
from app.api.session_pipeline import (
    ApproveReviewRequest,
    RoleCorrectionIn,
    TranscriptAnalyzeRequest,
    TranscriptResumeAfterRoleReviewRequest,
    TranscriptUtteranceIn,
    approve_review,
    analyze_transcript,
    resume_transcript_after_role_review,
    to_review_response,
)
from app.pipeline.types import ClinicalNoteDraft, DentistRole, NoteSentence, PipelineStatus
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


class SessionPipelineApiTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_analyze_transcript_stops_before_facts_when_role_gate_blocks(self) -> None:
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

        self.assertEqual(result.status, PipelineStatus.NEEDS_DENTIST_ROLE_REVIEW)
        self.assertEqual(result.stopped_at_stage, "role_assignment")
        self.assertIsNotNone(result.role_assignment)
        self.assertIsNone(result.clinical_facts)
        self.assertIsNone(result.clinical_note)
        self.assertEqual(result.procedures, [])
        self.assertEqual(result.code_suggestions, [])

        response = to_review_response(result)
        self.assertEqual(response.next_action, "review_speaker_roles")
        self.assertIsNotNone(response.role_review)
        self.assertIsNone(response.dentist_review)
        self.assertEqual(response.role_review.speakers[0].speaker_id, "A")

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
        self.assertEqual(payload["next_action"], "review_speaker_roles")
        self.assertIn("role_review", payload)
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
                {
                    "explanations": [
                        {"code": "FIX-KANAL-1K", "fit_reason": "Aday listesinde.", "caveat": None},
                        {"code": "FIX-KANAL-2K", "fit_reason": "Aday listesinde.", "caveat": None},
                        {"code": "FIX-KANAL-3K", "fit_reason": "Aday listesinde.", "caveat": None},
                    ],
                    "ambiguity_note": "Kanal sayısı net değil.",
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
        self.assertEqual(create_payload["review_state"], "needs_dentist_role_review")
        self.assertEqual(create_payload["next_action"], "review_speaker_roles")
        self.assertIsNone(create_payload["dentist_review"])
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
            json={"selected_codes": ["FIX-KANAL-2K"], "approved": True},
        )

        self.assertEqual(approve_response.status_code, 200)
        approve_payload = approve_response.json()
        self.assertEqual(approve_payload["review_state"], "approved_ready_for_export")
        self.assertEqual(approve_payload["next_action"], "export")
        self.assertIn("46 numarada derin çürük görüyorum.", approve_payload["export_payload"]["clinical_note_text"])
        self.assertEqual(approve_payload["export_payload"]["selected_codes"], ["FIX-KANAL-2K"])

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
                {
                    "explanations": [
                        {"code": "FIX-KANAL-1K", "fit_reason": "Aday listesinde.", "caveat": None},
                        {"code": "FIX-KANAL-2K", "fit_reason": "Aday listesinde.", "caveat": None},
                        {"code": "FIX-KANAL-3K", "fit_reason": "Aday listesinde.", "caveat": None},
                    ],
                    "ambiguity_note": "Kanal sayısı net değil.",
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
        self.assertEqual(len(result.code_suggestions[0].candidates), 3)
        self.assertEqual(len(result.code_suggestions[0].explanations), 3)

        response = to_review_response(result)
        self.assertEqual(response.next_action, "review_note_and_codes")
        self.assertIsNone(response.role_review)
        self.assertIsNotNone(response.dentist_review)
        self.assertEqual(len(response.dentist_review.procedures), 1)
        self.assertEqual(len(response.dentist_review.procedures[0].candidates), 3)

    def test_resume_after_role_review_blocks_when_correction_omits_speaker(self) -> None:
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

        self.assertEqual(result.status, PipelineStatus.NEEDS_DENTIST_ROLE_REVIEW)
        self.assertEqual(result.stopped_at_stage, "role_assignment")
        self.assertIsNone(result.clinical_facts)

        response = to_review_response(result)
        self.assertEqual(response.next_action, "review_speaker_roles")
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
                selected_codes=["FIX-KANAL-2K"],
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
        self.assertEqual(response.export_payload.selected_codes, ["FIX-KANAL-2K"])
        self.assertEqual(response.export_payload.audit.reviewer_user_id, "doctor-1")

    def test_audio_process_route_deletes_raw_audio_when_provider_not_configured(self) -> None:
        client = TestClient(app)

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
                "selected_codes": ["FIX-KANAL-2K"],
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

    def test_audio_provider_factory_defaults_to_safe_not_configured_provider(self) -> None:
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

    def test_audio_provider_factory_rejects_unknown_provider(self) -> None:
        with self.assertRaises(AudioProviderConfigurationError):
            create_audio_processing_provider("unknown-vendor")


if __name__ == "__main__":
    unittest.main()
