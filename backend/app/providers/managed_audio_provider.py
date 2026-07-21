"""Managed ASR/diarization adapter iskeleti.

Bu adapter vendor-specific değildir; production provider seçildiğinde beklenen
minimum HTTP sözleşmesini ve Klinia'nın normalize transcript formatını kurar.
Gerçek vendor endpoint'i bu sözleşmeye ince bir mapping katmanıyla bağlanır.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.pipeline.types import (
    AudioRef,
    SpeakerLabelledTranscript,
    SpeakerSegment,
    SpeakerSegments,
    Transcript,
    Utterance,
    Word,
)
from app.providers.audio_processing import (
    AudioProcessingProvider,
    AudioProviderConfigurationError,
    AudioProviderRuntimeError,
)

_ALLOWED_REGIONS = {"eu", "europe", "eea", "tr", "turkey", "turkiye", "türkiye"}


class ManagedAudioProviderConfig(BaseModel):
    endpoint_url: str
    api_key: str
    region: str = "eu"
    timeout_sec: float = 120.0
    language: str = "tr"

    @classmethod
    def from_env(cls) -> "ManagedAudioProviderConfig":
        endpoint_url = os.environ.get("KLINIA_AUDIO_ENDPOINT_URL", "").strip()
        api_key = os.environ.get("KLINIA_AUDIO_API_KEY", "").strip()
        region = os.environ.get("KLINIA_AUDIO_REGION", "eu").strip().lower()
        timeout_raw = os.environ.get("KLINIA_AUDIO_TIMEOUT_SEC", "120").strip()

        missing = []
        if not endpoint_url:
            missing.append("KLINIA_AUDIO_ENDPOINT_URL")
        if not api_key:
            missing.append("KLINIA_AUDIO_API_KEY")
        if missing:
            raise AudioProviderConfigurationError(
                "Managed audio provider eksik env: " + ", ".join(missing)
            )
        if region not in _ALLOWED_REGIONS:
            raise AudioProviderConfigurationError(
                "KLINIA_AUDIO_REGION AB/Türkiye uyumlu bir değer olmalı."
            )

        try:
            timeout_sec = float(timeout_raw)
        except ValueError as exc:
            raise AudioProviderConfigurationError("KLINIA_AUDIO_TIMEOUT_SEC sayısal olmalı.") from exc

        return cls(
            endpoint_url=endpoint_url,
            api_key=api_key,
            region=region,
            timeout_sec=timeout_sec,
        )


class ManagedAudioWordIn(BaseModel):
    text: str
    start_sec: float
    end_sec: float


class ManagedAudioUtteranceIn(BaseModel):
    speaker_id: str
    text: str
    start_sec: float
    end_sec: float
    words: list[ManagedAudioWordIn] = Field(default_factory=list)


class ManagedAudioResponseIn(BaseModel):
    session_id: Optional[str] = None
    language: str = "tr"
    utterances: list[ManagedAudioUtteranceIn] = Field(default_factory=list)


class ManagedHttpAudioProcessingProvider(AudioProcessingProvider):
    """Tek HTTP çağrısını Klinia'nın üç aşamalı provider arabirimine uyarlar."""

    def __init__(
        self,
        config: Optional[ManagedAudioProviderConfig] = None,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.config = config or ManagedAudioProviderConfig.from_env()
        self._client = client
        self._cache: dict[str, SpeakerLabelledTranscript] = {}

    def transcribe(self, audio: AudioRef) -> Transcript:
        aligned = self._ensure_aligned(audio)
        return Transcript(
            session_id=audio.session_id,
            language=self.config.language,
            words=[
                word
                for utterance in aligned.utterances
                for word in utterance.words
            ],
        )

    def diarize(self, audio: AudioRef) -> SpeakerSegments:
        aligned = self._ensure_aligned(audio)
        return SpeakerSegments(
            session_id=audio.session_id,
            segments=[
                SpeakerSegment(
                    speaker_id=utterance.speaker_id,
                    start_sec=utterance.start_sec,
                    end_sec=utterance.end_sec,
                )
                for utterance in aligned.utterances
            ],
        )

    def align(self, transcript: Transcript, diarization: SpeakerSegments) -> SpeakerLabelledTranscript:
        cached = self._cache.get(transcript.session_id)
        if cached is None:
            raise AudioProviderRuntimeError("Managed audio response cache bulunamadı.")
        return cached

    def _ensure_aligned(self, audio: AudioRef) -> SpeakerLabelledTranscript:
        cached = self._cache.get(audio.session_id)
        if cached is not None:
            return cached

        payload = self._post_audio(audio)
        aligned = normalize_managed_audio_response(audio.session_id, payload)
        self._cache[audio.session_id] = aligned
        return aligned

    def _post_audio(self, audio: AudioRef) -> dict[str, Any]:
        path = Path(audio.storage_uri)
        if not path.exists():
            raise AudioProviderRuntimeError("Geçici ses dosyası bulunamadı.")

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "X-Klinia-Region": self.config.region,
        }
        data = {
            "session_id": audio.session_id,
            "language": self.config.language,
            "response_format": "tandela_speaker_labelled_transcript_v1",
        }
        client = self._client or httpx.Client(timeout=self.config.timeout_sec)
        should_close = self._client is None
        try:
            with path.open("rb") as audio_file:
                files = {"audio": (path.name, audio_file, "application/octet-stream")}
                response = client.post(
                    self.config.endpoint_url,
                    data=data,
                    files=files,
                    headers=headers,
                )
            response.raise_for_status()
            parsed = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AudioProviderRuntimeError("Managed audio provider çağrısı başarısız.") from exc
        finally:
            if should_close:
                client.close()

        if not isinstance(parsed, dict):
            raise AudioProviderRuntimeError("Managed audio provider JSON obje döndürmedi.")
        return parsed


def normalize_managed_audio_response(
    expected_session_id: str,
    payload: dict[str, Any],
) -> SpeakerLabelledTranscript:
    """Provider JSON'unu Klinia'nın speaker-labelled transcript tipine çevirir."""

    try:
        parsed = ManagedAudioResponseIn.model_validate(payload)
    except ValidationError as exc:
        raise AudioProviderRuntimeError("Managed audio provider response sözleşmeye uymuyor.") from exc

    if not parsed.utterances:
        raise AudioProviderRuntimeError("Managed audio provider boş transcript döndürdü.")

    utterances = []
    for item in parsed.utterances:
        speaker_id = item.speaker_id.strip()
        text = item.text.strip()
        if not speaker_id or not text:
            raise AudioProviderRuntimeError("Managed audio provider eksik speaker_id/text döndürdü.")
        if item.end_sec < item.start_sec:
            raise AudioProviderRuntimeError("Managed audio provider geçersiz zaman aralığı döndürdü.")
        utterances.append(
            Utterance(
                speaker_id=speaker_id,
                text=text,
                start_sec=item.start_sec,
                end_sec=item.end_sec,
                words=[
                    Word(text=word.text, start_sec=word.start_sec, end_sec=word.end_sec)
                    for word in item.words
                ],
            )
        )

    return SpeakerLabelledTranscript(session_id=expected_session_id, utterances=utterances)
