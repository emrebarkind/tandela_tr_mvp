"""Audio upload → ASR provider iskeleti.

Gerçek ASR/diarization vendor'ı henüz seçilmediği için default provider
`not_configured` döner. Buna rağmen endpoint ham sesi geçici dosyaya yazar ve
her durumda siler; böylece retention kuralı en baştan API kontratına girer.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import shutil
import tempfile
import time
from typing import Optional
from uuid import uuid4

from fastapi import UploadFile
from pydantic import BaseModel, Field

from app.pipeline import stages
from app.pipeline.types import AudioRef, SpeakerLabelledTranscript
from app.providers.audio_processing import AudioProcessingProvider, AudioProviderRuntimeError


logger = logging.getLogger(__name__)


class AudioProcessResponse(BaseModel):
    session_id: str
    status: str
    raw_audio_deleted: bool
    provider_status: str
    transcript: Optional[SpeakerLabelledTranscript] = None
    message: str
    warnings: list[str] = Field(default_factory=list)


class AudioJobResponse(BaseModel):
    job_id: str
    session_id: str
    status: str
    result: Optional[AudioProcessResponse] = None
    error: Optional[str] = None
    created_at_utc: str
    updated_at_utc: str


_AUDIO_JOBS: dict[str, AudioJobResponse] = {}


def create_audio_processing_job(
    session_id: str,
    upload: UploadFile,
    provider: AudioProcessingProvider,
) -> AudioJobResponse:
    """Audio processing job kontratı.

    Şimdilik aynı request içinde çalışır; Celery/Redis eklendiğinde bu fonksiyon
    işi kuyruğa yazıp `queued` dönecek, status endpoint'i sonucu okuyacak.
    """

    job_id = f"audio_{uuid4().hex}"
    created_at = _now_utc()
    _AUDIO_JOBS[job_id] = AudioJobResponse(
        job_id=job_id,
        session_id=session_id,
        status="queued",
        created_at_utc=created_at,
        updated_at_utc=created_at,
    )
    _set_audio_job_status(job_id, "processing")

    result = process_uploaded_audio(session_id, upload, provider)
    status = "error" if result.status in {"provider_error", "processing_error"} else "done"
    job = _AUDIO_JOBS[job_id].model_copy(
        update={
            "status": status,
            "result": result,
            "error": result.message if status == "error" else None,
            "updated_at_utc": _now_utc(),
        }
    )
    _AUDIO_JOBS[job_id] = job
    return job


def get_audio_processing_job(job_id: str) -> Optional[AudioJobResponse]:
    return _AUDIO_JOBS.get(job_id)


def process_uploaded_audio(
    session_id: str,
    upload: UploadFile,
    provider: AudioProcessingProvider,
) -> AudioProcessResponse:
    temp_path: Optional[str] = None
    raw_audio_deleted = False
    suffix = _safe_suffix(upload.filename)
    response: Optional[AudioProcessResponse] = None

    try:
        with tempfile.NamedTemporaryFile(prefix=f"klinia_{session_id}_", suffix=suffix, delete=False) as tmp:
            temp_path = tmp.name
            shutil.copyfileobj(upload.file, tmp)

        audio_ref = AudioRef(session_id=session_id, storage_uri=temp_path)
        started_at = time.time()
        try:
            transcript = stages.transcribe_and_diarize_and_align(stages.preprocess_audio(audio_ref), provider)
        finally:
            logger.warning(
                "audio_timing stage=audio_processing_provider session_id=%s provider=%s duration_sec=%.3f",
                session_id,
                provider.__class__.__name__,
                time.time() - started_at,
            )
        response = AudioProcessResponse(
            session_id=session_id,
            status="transcript_ready",
            raw_audio_deleted=False,
            provider_status="configured",
            transcript=transcript,
            message="Ses işlendi; transkript üretildi.",
        )
    except NotImplementedError:
        response = AudioProcessResponse(
            session_id=session_id,
            status="provider_not_configured",
            raw_audio_deleted=False,
            provider_status="not_configured",
            transcript=None,
            message="ASR/diarization provider henüz yapılandırılmadı; ham ses saklanmadan silindi.",
            warnings=["Gerçek ASR vendor seçilene kadar bu endpoint transkript üretmez."],
        )
    except AudioProviderRuntimeError as exc:
        response = AudioProcessResponse(
            session_id=session_id,
            status="provider_error",
            raw_audio_deleted=False,
            provider_status="error",
            transcript=None,
            message="ASR/diarization provider sesi işleyemedi; ham ses saklanmadan silindi.",
            warnings=[str(exc)],
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
            raw_audio_deleted = True
        upload.file.close()

    if response is None:
        response = AudioProcessResponse(
            session_id=session_id,
            status="processing_error",
            raw_audio_deleted=raw_audio_deleted,
            provider_status="error",
            transcript=None,
            message="Ses işlenirken beklenmeyen hata oluştu; ham ses silindi.",
        )
    return response.model_copy(update={"raw_audio_deleted": raw_audio_deleted})


def _safe_suffix(filename: Optional[str]) -> str:
    if not filename or "." not in filename:
        return ".audio"
    suffix = "." + filename.rsplit(".", 1)[-1].lower()
    return suffix if len(suffix) <= 12 else ".audio"


def _set_audio_job_status(job_id: str, status: str) -> None:
    job = _AUDIO_JOBS[job_id]
    _AUDIO_JOBS[job_id] = job.model_copy(
        update={
            "status": status,
            "updated_at_utc": _now_utc(),
        }
    )


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()
