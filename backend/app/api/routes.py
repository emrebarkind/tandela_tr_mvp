"""FastAPI route yüzeyi."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.auth import create_access_token, verify_password
from app.api.audio_pipeline import (
    AudioJobResponse,
    AudioProcessResponse,
    create_audio_processing_job,
    get_audio_processing_job,
    process_uploaded_audio,
)
from app.api.auth import AuthContext, get_auth_context
from app.api.session_pipeline import (
    AudioProcessingReviewOut,
    ApproveReviewRequest,
    ManualFindingRequest,
    PipelineReviewResponse,
    ResumeRoleReviewRequest,
    SpeakerRolePatchRequest,
    TranscriptAnalyzeRequest,
    TranscriptResumeAfterRoleReviewRequest,
    approve_session_review,
    approve_review,
    analyze_transcript,
    add_manual_finding_to_session,
    create_session_from_transcript,
    patch_session_speaker_role,
    resume_session_after_role_review,
    resume_transcript_after_role_review,
    restore_session_result,
    to_review_response,
)
from app.db import create_database_engine, create_session_factory, init_database
from app.prompts.loader import load_system_prompt
from app.providers.llm import LLMProvider
from app.pipeline.orchestrator import run_perio_pipeline
from app.pipeline.types import PerioSessionResult, PipelineResult
from app.providers.audio_processing import (
    AudioProcessingProvider,
    AudioProviderConfigurationError,
    create_audio_processing_provider,
)
from app.repositories.session_repository import SessionRepository

router = APIRouter(prefix="/sessions", tags=["sessions"])
patients_router = APIRouter(prefix="/patients", tags=["patients"])
auth_router = APIRouter(prefix="/auth", tags=["auth"])
health_router = APIRouter(tags=["health"])
chat_router = APIRouter(prefix="/chat", tags=["chat"])
_ENGINE = create_database_engine()
_SESSION_FACTORY = create_session_factory(_ENGINE)
_DATABASE_INITIALIZED = False


@health_router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def get_llm_provider() -> LLMProvider:
    try:
        from app.providers.gemini_provider import GeminiLLMProvider

        return GeminiLLMProvider()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def get_audio_processing_provider() -> AudioProcessingProvider:
    try:
        return create_audio_processing_provider()
    except AudioProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def get_session_repository() -> Iterator[SessionRepository]:
    global _DATABASE_INITIALIZED
    if not _DATABASE_INITIALIZED:
        init_database(_ENGINE)
        _DATABASE_INITIALIZED = True
    db = _SESSION_FACTORY()
    try:
        yield SessionRepository(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    clinic_id: str
    user_id: str
    role: str


class PatientSummaryResponse(BaseModel):
    id: str
    initials: Optional[str] = None
    external_id: Optional[str] = None
    created_at: str
    last_session_at: Optional[str] = None
    session_count: int
    last_procedures: list[str]
    status: str


class PatientSessionSummaryResponse(BaseModel):
    id: str
    status: str
    session_type: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    procedures: list[str]


class PatientSessionsResponse(BaseModel):
    id: str
    initials: Optional[str] = None
    external_id: Optional[str] = None
    created_at: str
    sessions: list[PatientSessionSummaryResponse]


class ChatRequest(BaseModel):
    message: str
    patient_id: Optional[str] = None
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    source: str = "registered_clinical_records"


class PerioDictationRequest(BaseModel):
    dictation: str
    patient_id: Optional[str] = None


class PerioExportPayload(BaseModel):
    session_id: str
    perio_text: str
    audit: dict
    warning: str


class PerioApprovalResponse(BaseModel):
    session_id: str
    status: str
    review_state: str
    export_payload: PerioExportPayload


_PERIO_EXPORT_SITE_ORDER = ("DB", "B", "MB", "DL", "L", "ML")


def _format_perio_export(result: PerioSessionResult) -> str:
    measurements_by_tooth: dict[int, dict[str, object]] = {}
    for measurement in result.measurements:
        measurements_by_tooth.setdefault(measurement.tooth_number_fdi, {})[
            measurement.site.value
        ] = measurement
    summaries = {summary.tooth_number_fdi: summary for summary in result.tooth_summaries}
    tooth_numbers = sorted(set(measurements_by_tooth) | set(summaries))

    lines: list[str] = []
    for tooth_number in tooth_numbers:
        sites = measurements_by_tooth.get(tooth_number, {})

        def metric(field: str, *, suffix: str = "") -> str:
            values: list[str] = []
            for site in _PERIO_EXPORT_SITE_ORDER:
                measurement = sites.get(site)
                value = getattr(measurement, field, None) if measurement is not None else None
                values.append(f"{site}={'—' if value is None else f'{value}{suffix}'}")
            return " ".join(values)

        def flag(field: str) -> str:
            values: list[str] = []
            for site in _PERIO_EXPORT_SITE_ORDER:
                measurement = sites.get(site)
                value = getattr(measurement, field, None) if measurement is not None else None
                symbol = "—" if value is None else "+" if value else "-"
                values.append(f"{site}={symbol}")
            return " ".join(values)

        summary = summaries.get(tooth_number)
        mobility = summary.mobility_grade if summary is not None else None
        furcation_grade = summary.furcation_grade if summary is not None else None
        furcation_site = summary.furcation_site if summary is not None else None
        furcation = "—" if furcation_grade is None else str(furcation_grade)
        if furcation_site:
            furcation = f"{furcation} ({furcation_site})"
        lines.append(
            f"FDI {tooth_number}: Cep: {metric('pocket_depth_mm', suffix='mm')}; "
            f"Kanama: {flag('bleeding_on_probing')}; Plak: {flag('plaque')}; "
            f"Attachment: {metric('attachment_level_mm', suffix='mm')}; "
            f"Mobilite: {'—' if mobility is None else mobility}; Furkasyon: {furcation}"
        )

    if result.uncertain_items:
        lines.extend(["", "Kontrol Edilmeli:"])
        lines.extend(f"- {item}" for item in result.uncertain_items)
    return "\n".join(lines)


def _load_perio_review(
    repository: SessionRepository,
    session_id: str,
    *,
    clinic_id: str,
) -> tuple[object, dict, PerioSessionResult]:
    session = repository.latest_session(session_id, clinic_id=clinic_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session bulunamadı.")
    if session.session_type != "perio":
        raise HTTPException(status_code=409, detail="Bu session bir perio seansı değil.")
    snapshot = repository.get_review_snapshot(session_id, clinic_id=clinic_id)
    perio_payload = snapshot.get("perio_result") if snapshot else None
    if perio_payload is None:
        raise HTTPException(status_code=409, detail="Onaylanacak perio taslağı bulunamadı.")
    return session, snapshot, PerioSessionResult.model_validate(perio_payload)


def _transcript_snapshot(result) -> list[dict]:
    if result.speaker_labelled_transcript is None:
        return []
    return [utterance.model_dump(mode="json") for utterance in result.speaker_labelled_transcript.utterances]


def _save_clinical_review_snapshot(
    repository: SessionRepository,
    result,
    *,
    clinic_id: str,
    response: Optional[PipelineReviewResponse] = None,
) -> PipelineReviewResponse:
    review = response or to_review_response(result)
    repository.save_review_snapshot(
        result.session_id,
        {
            "snapshot_version": 1,
            "session_id": result.session_id,
            "session_type": "clinical_note",
            "transcript": _transcript_snapshot(result),
            "clinical_review": review.model_dump(mode="json"),
            "clinical_pipeline": result.model_dump(mode="json"),
            "perio_result": None,
        },
        clinic_id=clinic_id,
    )
    return review


def _restore_clinical_review_state(
    repository: SessionRepository,
    session_id: str,
    *,
    clinic_id: str,
) -> None:
    snapshot = repository.get_review_snapshot(session_id, clinic_id=clinic_id)
    pipeline_payload = snapshot.get("clinical_pipeline") if snapshot else None
    if pipeline_payload:
        restore_session_result(PipelineResult.model_validate(pipeline_payload))


@auth_router.post("/login", response_model=LoginResponse)
def login_endpoint(
    request: LoginRequest,
    repository: SessionRepository = Depends(get_session_repository),
) -> LoginResponse:
    user = repository.find_user_by_email(request.email)
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email veya şifre hatalı.")
    token = create_access_token(user_id=user.id, clinic_id=user.clinic_id, role=user.role)
    return LoginResponse(
        access_token=token,
        clinic_id=user.clinic_id,
        user_id=user.id,
        role=user.role,
    )


@patients_router.get("", response_model=list[PatientSummaryResponse])
def list_patients_endpoint(
    q: Optional[str] = None,
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> list[PatientSummaryResponse]:
    return [
        PatientSummaryResponse(**patient)
        for patient in repository.list_patients(clinic_id=auth.clinic_id, query=q)
    ]


@patients_router.get("/{patient_id}/sessions", response_model=PatientSessionsResponse)
def get_patient_sessions_endpoint(
    patient_id: str,
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> PatientSessionsResponse:
    patient = repository.get_patient_sessions(patient_id, clinic_id=auth.clinic_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Hasta bulunamadı.")
    return PatientSessionsResponse(**patient)


@chat_router.post("", response_model=ChatResponse)
def chat_endpoint(
    request: ChatRequest,
    llm_provider: LLMProvider = Depends(get_llm_provider),
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> ChatResponse:
    context = _registered_record_context(request, repository, clinic_id=auth.clinic_id)
    if not context.strip() or not request.message.strip():
        return ChatResponse(answer="Kayıtlarda bulunmuyor.")

    raw = llm_provider.complete(
        load_system_prompt("assistant_chat.md"),
        "\n\n".join(
            [
                "KAYITLI_VERI:",
                context,
                "SORU:",
                request.message.strip(),
            ]
        ),
    )
    try:
        parsed = json.loads(raw)
    except ValueError:
        return ChatResponse(answer="Kayıtlarda bulunmuyor.")
    answer = str(parsed.get("answer") or "").strip()
    return ChatResponse(answer=answer or "Kayıtlarda bulunmuyor.")


@router.post("", response_model=PipelineReviewResponse)
def create_session_endpoint(
    request: TranscriptAnalyzeRequest,
    llm_provider: LLMProvider = Depends(get_llm_provider),
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> PipelineReviewResponse:
    try:
        result = create_session_from_transcript(request, llm_provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        repository.save_pipeline_result(
            result,
            clinic_id=auth.clinic_id,
            actor_user_id=auth.user_id,
            transcript_source="manual_transcript",
            patient_id=request.patient_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _save_clinical_review_snapshot(repository, result, clinic_id=auth.clinic_id)


@router.get("/{session_id}/review")
def get_session_review_endpoint(
    session_id: str,
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    snapshot = repository.get_review_snapshot(session_id, clinic_id=auth.clinic_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Session review snapshot bulunamadı.")
    return snapshot


@router.get("/{session_id}")
def get_session_endpoint(
    session_id: str,
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    session = repository.get_session(session_id, clinic_id=auth.clinic_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session bulunamadı.")
    return session


@router.post("/{session_id}/perio", response_model=PerioSessionResult)
def extract_perio_session_endpoint(
    session_id: str,
    request: PerioDictationRequest,
    llm_provider: LLMProvider = Depends(get_llm_provider),
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> PerioSessionResult:
    existing_session = repository.latest_session(session_id, clinic_id=auth.clinic_id)
    patient_id = request.patient_id or (existing_session.patient_id if existing_session else None)
    if not patient_id:
        raise HTTPException(status_code=400, detail="Perio seansı için patient_id gerekli.")
    try:
        repository.upsert_session(
            session_id,
            status="draft",
            current_stage="transcript",
            clinic_id=auth.clinic_id,
            dentist_id=auth.user_id,
            patient_id=patient_id,
            session_type="perio",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        result = run_perio_pipeline(request.dictation, llm_provider)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    repository.save_transcript(
        session_id,
        [{"speaker_id": "dentist", "text": request.dictation.strip()}],
        source="perio_dictation",
        clinic_id=auth.clinic_id,
        actor_user_id=auth.user_id,
    )
    repository.upsert_session(
        session_id,
        status="draft",
        current_stage="perio_review",
        clinic_id=auth.clinic_id,
        dentist_id=auth.user_id,
        patient_id=patient_id,
        session_type="perio",
    )
    repository.add_audit_log(
        user_id=auth.user_id,
        session_id=session_id,
        clinic_id=auth.clinic_id,
        action="perio_extracted",
        entity_type="perio_session_result",
        entity_id=session_id,
        source="ai",
        metadata_json={
            "measurement_count": len(result.measurements),
            "tooth_summary_count": len(result.tooth_summaries),
            "uncertain_item_count": len(result.uncertain_items),
        },
    )
    repository.save_review_snapshot(
        session_id,
        {
            "snapshot_version": 1,
            "session_id": session_id,
            "session_type": "perio",
            "transcript": [{"speaker_id": "dentist", "text": request.dictation.strip()}],
            "clinical_review": None,
            "clinical_pipeline": None,
            "perio_result": result.model_dump(mode="json"),
        },
        clinic_id=auth.clinic_id,
    )
    return result


@router.post("/{session_id}/perio/approve", response_model=PerioApprovalResponse)
def approve_perio_session_endpoint(
    session_id: str,
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> PerioApprovalResponse:
    session, snapshot, result = _load_perio_review(
        repository, session_id, clinic_id=auth.clinic_id
    )
    existing_approval = snapshot.get("perio_approval")
    if session.status == "approved" and existing_approval:
        return PerioApprovalResponse.model_validate(existing_approval)

    approved_at = datetime.now(timezone.utc).isoformat()
    export_payload = PerioExportPayload(
        session_id=session_id,
        perio_text=_format_perio_export(result),
        audit={
            "action": "perio_approved",
            "reviewer_user_id": auth.user_id,
            "approved": True,
            "created_at_utc": approved_at,
            "source": "dentist",
        },
        warning="Hekim tarafından onaylanmış periodontal kayıt çıktısıdır.",
    )
    response = PerioApprovalResponse(
        session_id=session_id,
        status="approved",
        review_state="approved",
        export_payload=export_payload,
    )
    repository.upsert_session(
        session_id,
        status="approved",
        current_stage="ready_for_export",
        clinic_id=auth.clinic_id,
        dentist_id=auth.user_id,
        patient_id=session.patient_id,
        session_type="perio",
    )
    repository.add_audit_log(
        user_id=auth.user_id,
        session_id=session_id,
        clinic_id=auth.clinic_id,
        action="perio_approved",
        entity_type="perio_session_result",
        entity_id=session_id,
        source="dentist",
        metadata_json={
            "measurement_count": len(result.measurements),
            "tooth_summary_count": len(result.tooth_summaries),
            "approved_at_utc": approved_at,
        },
    )
    updated_snapshot = {
        **snapshot,
        "perio_approval": response.model_dump(mode="json"),
    }
    repository.save_review_snapshot(session_id, updated_snapshot, clinic_id=auth.clinic_id)
    return response


@router.get("/{session_id}/perio/export", response_model=PerioExportPayload)
def export_perio_session_endpoint(
    session_id: str,
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> PerioExportPayload:
    session, snapshot, _ = _load_perio_review(
        repository, session_id, clinic_id=auth.clinic_id
    )
    approval = snapshot.get("perio_approval")
    if session.status != "approved" or not approval:
        raise HTTPException(
            status_code=409,
            detail="Perio taslağı hekim tarafından onaylanmadan export edilemez.",
        )
    return PerioApprovalResponse.model_validate(approval).export_payload


@router.post("/{session_id}/resume-role-review", response_model=PipelineReviewResponse)
def resume_session_role_review_endpoint(
    session_id: str,
    request: ResumeRoleReviewRequest,
    llm_provider: LLMProvider = Depends(get_llm_provider),
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> PipelineReviewResponse:
    _restore_clinical_review_state(repository, session_id, clinic_id=auth.clinic_id)
    try:
        result = resume_session_after_role_review(session_id, request, llm_provider)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session bulunamadı.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    repository.save_pipeline_result(
        result,
        clinic_id=auth.clinic_id,
        actor_user_id=auth.user_id,
        transcript_source="role_reviewed_transcript",
    )
    return _save_clinical_review_snapshot(repository, result, clinic_id=auth.clinic_id)


@router.patch("/{session_id}/speaker-role", response_model=PipelineReviewResponse)
def patch_session_speaker_role_endpoint(
    session_id: str,
    request: SpeakerRolePatchRequest,
    llm_provider: LLMProvider = Depends(get_llm_provider),
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> PipelineReviewResponse:
    _restore_clinical_review_state(repository, session_id, clinic_id=auth.clinic_id)
    try:
        result = patch_session_speaker_role(session_id, request, llm_provider)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session bulunamadı.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    repository.save_pipeline_result(
        result,
        clinic_id=auth.clinic_id,
        actor_user_id=auth.user_id,
        transcript_source="speaker_role_patch",
    )
    return _save_clinical_review_snapshot(repository, result, clinic_id=auth.clinic_id)


@router.post("/{session_id}/findings", response_model=PipelineReviewResponse)
def add_manual_finding_endpoint(
    session_id: str,
    request: ManualFindingRequest,
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> PipelineReviewResponse:
    _restore_clinical_review_state(repository, session_id, clinic_id=auth.clinic_id)
    try:
        result = add_manual_finding_to_session(session_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session bulunamadı.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    repository.add_audit_log(
        user_id=auth.user_id,
        session_id=session_id,
        clinic_id=auth.clinic_id,
        action="manual_finding_added",
        entity_type="procedure",
        entity_id=None,
        source="manual",
        metadata_json=request.model_dump(mode="json"),
    )
    return _save_clinical_review_snapshot(repository, result, clinic_id=auth.clinic_id)


@router.post("/transcripts/analyze", response_model=PipelineReviewResponse)
def analyze_transcript_endpoint(
    request: TranscriptAnalyzeRequest,
    llm_provider: LLMProvider = Depends(get_llm_provider),
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> PipelineReviewResponse:
    result = analyze_transcript(request, llm_provider)
    response = to_review_response(result)
    session_id = result.session_id
    repository.save_transcript(
        session_id,
        [utterance.model_dump(mode="json") for utterance in request.utterances],
        source="manual_transcript",
        clinic_id=auth.clinic_id,
        actor_user_id=auth.user_id,
    )
    repository.upsert_session(
        session_id,
        status=result.status.value,
        current_stage=result.stopped_at_stage,
        clinic_id=auth.clinic_id,
    )
    if result.clinical_note is not None:
        repository.save_clinical_note(
            session_id,
            result.clinical_note,
            clinic_id=auth.clinic_id,
            actor_user_id=auth.user_id,
        )
    return _save_clinical_review_snapshot(
        repository, result, clinic_id=auth.clinic_id, response=response
    )


@router.post("/transcripts/resume-after-role-review", response_model=PipelineReviewResponse)
def resume_after_role_review_endpoint(
    request: TranscriptResumeAfterRoleReviewRequest,
    llm_provider: LLMProvider = Depends(get_llm_provider),
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> PipelineReviewResponse:
    result = resume_transcript_after_role_review(request, llm_provider)
    response = to_review_response(result)
    session_id = result.session_id
    repository.save_transcript(
        session_id,
        [utterance.model_dump(mode="json") for utterance in request.utterances],
        source="role_reviewed_transcript",
        clinic_id=auth.clinic_id,
        actor_user_id=auth.user_id,
    )
    repository.upsert_session(
        session_id,
        status=result.status.value,
        current_stage=result.stopped_at_stage,
        clinic_id=auth.clinic_id,
    )
    if result.clinical_note is not None:
        repository.save_clinical_note(
            session_id,
            result.clinical_note,
            clinic_id=auth.clinic_id,
            actor_user_id=auth.user_id,
        )
    return _save_clinical_review_snapshot(
        repository, result, clinic_id=auth.clinic_id, response=response
    )


@router.post("/reviews/approve", response_model=PipelineReviewResponse)
def approve_review_endpoint(
    request: ApproveReviewRequest,
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> PipelineReviewResponse:
    trusted_request = request.model_copy(update={"reviewer_user_id": auth.user_id})
    result = approve_review(trusted_request)
    response = to_review_response(result)
    if trusted_request.approved_note is not None:
        repository.save_clinical_note(
            trusted_request.session_id,
            trusted_request.approved_note,
            status="approved",
            clinic_id=auth.clinic_id,
            actor_user_id=auth.user_id,
        )
    repository.save_review_approval(
        trusted_request.session_id,
        approved=trusted_request.approved,
        selected_codes=trusted_request.selected_codes,
        reviewer_user_id=auth.user_id,
        export_payload=response.export_payload,
        clinic_id=auth.clinic_id,
    )
    return response


@router.post("/{session_id}/approve", response_model=PipelineReviewResponse)
def approve_session_endpoint(
    session_id: str,
    request: ApproveReviewRequest,
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> PipelineReviewResponse:
    trusted_request = request.model_copy(update={"reviewer_user_id": auth.user_id})
    _restore_clinical_review_state(repository, session_id, clinic_id=auth.clinic_id)
    try:
        result = approve_session_review(session_id, trusted_request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session bulunamadı.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    response = to_review_response(result)
    if trusted_request.approved_note is not None:
        repository.save_clinical_note(
            session_id,
            trusted_request.approved_note,
            status="approved",
            clinic_id=auth.clinic_id,
            actor_user_id=auth.user_id,
        )
    repository.save_review_approval(
        session_id,
        approved=trusted_request.approved,
        selected_codes=trusted_request.selected_codes,
        reviewer_user_id=auth.user_id,
        export_payload=response.export_payload,
        clinic_id=auth.clinic_id,
    )
    return _save_clinical_review_snapshot(
        repository, result, clinic_id=auth.clinic_id, response=response
    )


@router.post("/{session_id}/audio", response_model=PipelineReviewResponse)
def session_audio_endpoint(
    session_id: str,
    audio: UploadFile = File(...),
    patient_id: Optional[str] = Form(default=None),
    audio_provider: AudioProcessingProvider = Depends(get_audio_processing_provider),
    llm_provider: LLMProvider = Depends(get_llm_provider),
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> PipelineReviewResponse:
    audio_result = process_uploaded_audio(session_id, audio, audio_provider)
    audio_out = AudioProcessingReviewOut(
        status=audio_result.status,
        raw_audio_deleted=audio_result.raw_audio_deleted,
        provider_status=audio_result.provider_status,
        message=audio_result.message,
        warnings=audio_result.warnings,
        transcript=audio_result.transcript,
    )
    if audio_result.transcript is None or audio_result.status != "transcript_ready":
        raise HTTPException(
            status_code=503,
            detail=audio_out.model_dump(mode="json"),
        )

    request = TranscriptAnalyzeRequest(
        session_id=session_id,
        patient_id=patient_id,
        utterances=[
            {
                "speaker_id": utterance.speaker_id,
                "text": utterance.text,
                "start_sec": utterance.start_sec,
                "end_sec": utterance.end_sec,
            }
            for utterance in audio_result.transcript.utterances
        ],
    )
    result = create_session_from_transcript(request, llm_provider)
    repository.save_pipeline_result(
        result,
        clinic_id=auth.clinic_id,
        actor_user_id=auth.user_id,
        transcript_source="audio",
        patient_id=patient_id,
    )
    response = to_review_response(result).model_copy(update={"audio_processing": audio_out})
    return _save_clinical_review_snapshot(
        repository, result, clinic_id=auth.clinic_id, response=response
    )


@router.post("/audio/process", response_model=AudioProcessResponse)
def process_audio_endpoint(
    session_id: str = Form(...),
    audio: UploadFile = File(...),
    provider: AudioProcessingProvider = Depends(get_audio_processing_provider),
    auth: AuthContext = Depends(get_auth_context),
) -> AudioProcessResponse:
    _ = auth
    return process_uploaded_audio(session_id, audio, provider)


@router.post("/audio/jobs", response_model=AudioJobResponse)
def create_audio_job_endpoint(
    session_id: str = Form(...),
    audio: UploadFile = File(...),
    provider: AudioProcessingProvider = Depends(get_audio_processing_provider),
    auth: AuthContext = Depends(get_auth_context),
) -> AudioJobResponse:
    _ = auth
    return create_audio_processing_job(session_id, audio, provider)


@router.get("/audio/jobs/{job_id}", response_model=AudioJobResponse)
def get_audio_job_endpoint(
    job_id: str,
    auth: AuthContext = Depends(get_auth_context),
) -> AudioJobResponse:
    _ = auth
    job = get_audio_processing_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Audio job bulunamadı.")
    return job


def _registered_record_context(
    request: ChatRequest,
    repository: SessionRepository,
    *,
    clinic_id: str,
) -> str:
    chunks: list[str] = []
    if request.session_id:
        session = repository.get_session(request.session_id, clinic_id=clinic_id)
        if session is not None:
            chunks.append(_session_context(session))
    if request.patient_id:
        patient = repository.get_patient_sessions(request.patient_id, clinic_id=clinic_id)
        if patient is not None:
            chunks.append(json.dumps(patient, ensure_ascii=False, default=str))
    return "\n\n".join(chunk for chunk in chunks if chunk.strip())


def _session_context(session: dict) -> str:
    compact = {
        "session_id": session.get("id"),
        "status": session.get("status"),
        "current_stage": session.get("current_stage"),
        "transcripts": session.get("transcripts", [])[-2:],
        "clinical_notes": session.get("clinical_notes", [])[-2:],
        "code_suggestions": session.get("code_suggestions", []),
    }
    return json.dumps(compact, ensure_ascii=False, default=str)
