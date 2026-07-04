"""FastAPI route yüzeyi."""

from __future__ import annotations

from collections.abc import Iterator

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
    PipelineReviewResponse,
    ResumeRoleReviewRequest,
    TranscriptAnalyzeRequest,
    TranscriptResumeAfterRoleReviewRequest,
    approve_session_review,
    approve_review,
    analyze_transcript,
    create_session_from_transcript,
    resume_session_after_role_review,
    resume_transcript_after_role_review,
    to_review_response,
)
from app.db import create_database_engine, create_session_factory, init_database
from app.providers.llm import LLMProvider
from app.providers.audio_processing import (
    AudioProcessingProvider,
    AudioProviderConfigurationError,
    create_audio_processing_provider,
)
from app.repositories.session_repository import SessionRepository

router = APIRouter(prefix="/sessions", tags=["sessions"])
auth_router = APIRouter(prefix="/auth", tags=["auth"])
health_router = APIRouter(tags=["health"])
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
    repository.save_pipeline_result(
        result,
        clinic_id=auth.clinic_id,
        actor_user_id=auth.user_id,
        transcript_source="manual_transcript",
    )
    return to_review_response(result)


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


@router.post("/{session_id}/resume-role-review", response_model=PipelineReviewResponse)
def resume_session_role_review_endpoint(
    session_id: str,
    request: ResumeRoleReviewRequest,
    llm_provider: LLMProvider = Depends(get_llm_provider),
    repository: SessionRepository = Depends(get_session_repository),
    auth: AuthContext = Depends(get_auth_context),
) -> PipelineReviewResponse:
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
    return to_review_response(result)


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
    return response


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
    return response


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
    return response


@router.post("/{session_id}/audio", response_model=PipelineReviewResponse)
def session_audio_endpoint(
    session_id: str,
    audio: UploadFile = File(...),
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
    )
    return to_review_response(result).model_copy(update={"audio_processing": audio_out})


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
