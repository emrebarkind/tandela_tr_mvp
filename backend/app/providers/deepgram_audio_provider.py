"""Deepgram Nova audio transcription/diarization provider.

Vendor decision for Phase C: Deepgram with the EU API endpoint. This adapter
keeps Deepgram-specific HTTP and response mapping behind AudioProcessingProvider.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional, Union

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
from app.providers.gemini_provider import _load_env_file

_ENV_FILE = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
_DEFAULT_BASE_URL = "https://api.eu.deepgram.com"


class DeepgramAudioProviderConfig(BaseModel):
    api_key: str
    base_url: str = _DEFAULT_BASE_URL
    model: str = "nova-3"
    language: str = "tr"
    timeout_sec: float = 180.0

    @classmethod
    def from_env(cls) -> "DeepgramAudioProviderConfig":
        key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
        if not key:
            _load_env_file(_ENV_FILE)
            key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
        if not key:
            raise AudioProviderConfigurationError("DEEPGRAM_API_KEY yok; Deepgram provider başlatılamadı.")

        base_url = os.environ.get("DEEPGRAM_BASE_URL", _DEFAULT_BASE_URL).strip().rstrip("/")
        if base_url != _DEFAULT_BASE_URL:
            raise AudioProviderConfigurationError("Deepgram için AB endpoint zorunlu: https://api.eu.deepgram.com")

        timeout_raw = os.environ.get("DEEPGRAM_TIMEOUT_SEC", "180").strip()
        try:
            timeout_sec = float(timeout_raw)
        except ValueError as exc:
            raise AudioProviderConfigurationError("DEEPGRAM_TIMEOUT_SEC sayısal olmalı.") from exc

        return cls(
            api_key=key,
            base_url=base_url,
            model=os.environ.get("DEEPGRAM_MODEL", "nova-3").strip() or "nova-3",
            language=os.environ.get("DEEPGRAM_LANGUAGE", "tr").strip() or "tr",
            timeout_sec=timeout_sec,
        )


class DeepgramWordIn(BaseModel):
    word: str = ""
    punctuated_word: Optional[str] = None
    start: float
    end: float
    speaker: Optional[Union[int, str]] = None


class DeepgramUtteranceIn(BaseModel):
    start: float
    end: float
    transcript: str
    speaker: Optional[Union[int, str]] = None
    words: list[DeepgramWordIn] = Field(default_factory=list)


class DeepgramAlternativeIn(BaseModel):
    transcript: str = ""
    words: list[DeepgramWordIn] = Field(default_factory=list)


class DeepgramChannelIn(BaseModel):
    alternatives: list[DeepgramAlternativeIn] = Field(default_factory=list)


class DeepgramResultsIn(BaseModel):
    channels: list[DeepgramChannelIn] = Field(default_factory=list)
    utterances: list[DeepgramUtteranceIn] = Field(default_factory=list)


class DeepgramResponseIn(BaseModel):
    results: DeepgramResultsIn


class DeepgramAudioProcessingProvider(AudioProcessingProvider):
    def __init__(
        self,
        config: Optional[DeepgramAudioProviderConfig] = None,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.config = config or DeepgramAudioProviderConfig.from_env()
        self._client = client
        self._cache: dict[str, SpeakerLabelledTranscript] = {}

    def transcribe(self, audio: AudioRef) -> Transcript:
        aligned = self._ensure_aligned(audio)
        return Transcript(
            session_id=audio.session_id,
            language=self.config.language,
            words=[word for utterance in aligned.utterances for word in utterance.words],
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
            raise AudioProviderRuntimeError("Deepgram response cache bulunamadı.")
        return cached

    def _ensure_aligned(self, audio: AudioRef) -> SpeakerLabelledTranscript:
        cached = self._cache.get(audio.session_id)
        if cached is not None:
            return cached

        payload = self._post_audio(audio)
        aligned = normalize_deepgram_audio_response(audio.session_id, payload)
        self._cache[audio.session_id] = aligned
        return aligned

    def _post_audio(self, audio: AudioRef) -> dict[str, Any]:
        path = Path(audio.storage_uri)
        if not path.exists():
            raise AudioProviderRuntimeError("Geçici ses dosyası bulunamadı.")

        params = {
            "model": self.config.model,
            "language": self.config.language,
            "diarize": "true",
            "utterances": "true",
            "punctuate": "true",
            "smart_format": "true",
        }
        headers = {
            "Authorization": f"Token {self.config.api_key}",
            "Content-Type": _mime_type_for_path(path),
        }
        client = self._client or httpx.Client(timeout=self.config.timeout_sec)
        should_close = self._client is None
        try:
            with path.open("rb") as audio_file:
                response = client.post(
                    f"{self.config.base_url}/v1/listen",
                    params=params,
                    headers=headers,
                    content=audio_file.read(),
                )
            response.raise_for_status()
            parsed = response.json()
        except httpx.HTTPStatusError as exc:
            detail = _safe_deepgram_error_detail(exc.response)
            raise AudioProviderRuntimeError(f"Deepgram provider çağrısı başarısız: {detail}") from exc
        except httpx.HTTPError as exc:
            raise AudioProviderRuntimeError("Deepgram provider çağrısı başarısız: ağ hatası.") from exc
        except ValueError as exc:
            raise AudioProviderRuntimeError("Deepgram provider geçersiz JSON döndürdü.") from exc
        finally:
            if should_close:
                client.close()

        if not isinstance(parsed, dict):
            raise AudioProviderRuntimeError("Deepgram provider JSON obje döndürmedi.")
        return parsed


def normalize_deepgram_audio_response(expected_session_id: str, payload: dict[str, Any]) -> SpeakerLabelledTranscript:
    try:
        parsed = DeepgramResponseIn.model_validate(payload)
    except ValidationError as exc:
        raise AudioProviderRuntimeError("Deepgram response sözleşmeye uymuyor.") from exc

    utterances = _utterances_from_deepgram_utterances(parsed.results.utterances)
    if not utterances:
        words = _words_from_channels(parsed.results.channels)
        utterances = _utterances_from_words(words)

    if not utterances:
        raise AudioProviderRuntimeError("Deepgram provider boş transcript döndürdü.")

    return SpeakerLabelledTranscript(session_id=expected_session_id, utterances=utterances)


def _utterances_from_deepgram_utterances(items: list[DeepgramUtteranceIn]) -> list[Utterance]:
    utterances: list[Utterance] = []
    for item in items:
        text = item.transcript.strip()
        if not text:
            continue
        words = [_word_from_deepgram_word(word) for word in item.words]
        utterances.append(
            Utterance(
                speaker_id=_speaker_id(item.speaker),
                text=text,
                start_sec=round(item.start, 2),
                end_sec=round(item.end, 2),
                words=words or _words_for_text(text, item.start, item.end),
            )
        )
    return utterances


def _words_from_channels(channels: list[DeepgramChannelIn]) -> list[DeepgramWordIn]:
    if not channels or not channels[0].alternatives:
        return []
    return channels[0].alternatives[0].words


def _utterances_from_words(words: list[DeepgramWordIn]) -> list[Utterance]:
    utterances: list[Utterance] = []
    current: list[DeepgramWordIn] = []
    current_speaker: Optional[Union[int, str]] = None

    for word in words:
        speaker = word.speaker if word.speaker is not None else 0
        if current and speaker != current_speaker:
            utterances.append(_utterance_from_word_group(current_speaker, current))
            current = []
        current_speaker = speaker
        current.append(word)

    if current:
        utterances.append(_utterance_from_word_group(current_speaker, current))
    return utterances


def _utterance_from_word_group(speaker: Optional[Union[int, str]], words: list[DeepgramWordIn]) -> Utterance:
    text = " ".join((word.punctuated_word or word.word).strip() for word in words if (word.punctuated_word or word.word).strip())
    if not text:
        text = " ".join(word.word for word in words).strip()
    return Utterance(
        speaker_id=_speaker_id(speaker),
        text=text,
        start_sec=round(words[0].start, 2),
        end_sec=round(words[-1].end, 2),
        words=[_word_from_deepgram_word(word) for word in words],
    )


def _speaker_id(speaker: Optional[Union[int, str]]) -> str:
    if speaker is None:
        return "A"
    try:
        index = int(speaker)
    except (TypeError, ValueError):
        raw = str(speaker).strip().upper()
        return raw if raw else "A"
    return chr(ord("A") + max(0, min(index, 25)))


def _word_from_deepgram_word(word: DeepgramWordIn) -> Word:
    return Word(
        text=(word.punctuated_word or word.word).strip() or word.word,
        start_sec=round(word.start, 2),
        end_sec=round(word.end, 2),
    )


def _words_for_text(text: str, start_sec: float, end_sec: float) -> list[Word]:
    raw_words = text.split()
    if not raw_words:
        return []
    duration = max(0.05, (end_sec - start_sec) / len(raw_words))
    cursor = start_sec
    words = []
    for raw_word in raw_words:
        word_end = min(end_sec, cursor + duration)
        words.append(Word(text=raw_word, start_sec=round(cursor, 2), end_sec=round(word_end, 2)))
        cursor = word_end
    return words


def _mime_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".webm":
        return "audio/webm"
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".m4a":
        return "audio/mp4"
    if suffix in {".aif", ".aiff"}:
        return "audio/aiff"
    return "application/octet-stream"


def _safe_deepgram_error_detail(response: httpx.Response) -> str:
    text = response.text.strip().replace("\n", " ")
    if len(text) > 240:
        text = f"{text[:240]}..."
    return f"HTTP {response.status_code}" + (f" - {text}" if text else "")
