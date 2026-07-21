"""Gemini-backed audio transcription/diarization provider for demo MVP.

Bu provider gerçek ses dosyasını modele gönderir ve Klinia'nın
speaker-labelled transcript formatına normalize eder. Demo hedefi içindir:
ayrı bir ASR/diarization vendor key'i olmadan mevcut GEMINI_API_KEY ile
ses→transcript→analiz akışını gerçek kayda bağlar.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from google import genai
from google.genai import types
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
from app.providers.gemini_provider import _load_env_file, _strip_json_fences

_ENV_FILE = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
_DEFAULT_MODEL = "gemini-3.5-flash"


class GeminiAudioUtteranceIn(BaseModel):
    speaker_id: str
    text: str
    start_sec: Optional[float] = None
    end_sec: Optional[float] = None


class GeminiAudioResponseIn(BaseModel):
    utterances: list[GeminiAudioUtteranceIn] = Field(default_factory=list)


class GeminiAudioProcessingProvider(AudioProcessingProvider):
    """Gemini multimodal call wrapped behind AudioProcessingProvider."""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None) -> None:
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            _load_env_file(_ENV_FILE)
            key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise AudioProviderConfigurationError("GEMINI_API_KEY yok; Gemini audio provider başlatılamadı.")
        self._client = genai.Client(api_key=key)
        self._model = model or os.environ.get("GEMINI_AUDIO_MODEL", _DEFAULT_MODEL)
        self._cache: dict[str, SpeakerLabelledTranscript] = {}

    def transcribe(self, audio: AudioRef) -> Transcript:
        aligned = self._ensure_aligned(audio)
        return Transcript(
            session_id=audio.session_id,
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
            raise AudioProviderRuntimeError("Gemini audio response cache bulunamadı.")
        return cached

    def _ensure_aligned(self, audio: AudioRef) -> SpeakerLabelledTranscript:
        cached = self._cache.get(audio.session_id)
        if cached is not None:
            return cached

        path = Path(audio.storage_uri)
        if not path.exists():
            raise AudioProviderRuntimeError("Geçici ses dosyası bulunamadı.")

        mime_type = _mime_type_for_path(path)
        prompt = _audio_transcript_prompt()
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[
                    types.Part.from_text(text=prompt),
                    types.Part.from_bytes(data=path.read_bytes(), mime_type=mime_type),
                ],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
        except Exception as exc:
            raise AudioProviderRuntimeError("Gemini audio provider çağrısı başarısız.") from exc

        try:
            payload = _loads_json_object(response.text or "")
        except json.JSONDecodeError as exc:
            raise AudioProviderRuntimeError("Gemini audio provider JSON döndürmedi.") from exc
        if not isinstance(payload, dict):
            raise AudioProviderRuntimeError("Gemini audio provider JSON obje döndürmedi.")

        aligned = normalize_gemini_audio_response(audio.session_id, payload)
        self._cache[audio.session_id] = aligned
        return aligned


def normalize_gemini_audio_response(
    expected_session_id: str,
    payload: dict[str, Any],
) -> SpeakerLabelledTranscript:
    try:
        parsed = GeminiAudioResponseIn.model_validate(payload)
    except ValidationError as exc:
        raise AudioProviderRuntimeError("Gemini audio response sözleşmeye uymuyor.") from exc

    if not parsed.utterances:
        raise AudioProviderRuntimeError("Gemini audio provider boş transcript döndürdü.")

    utterances: list[Utterance] = []
    cursor = 0.0
    speaker_map: dict[str, str] = {}
    for item in parsed.utterances:
        speaker_id = _normalize_speaker_id(item.speaker_id, speaker_map)
        text = item.text.strip()
        if not speaker_id or not text:
            raise AudioProviderRuntimeError("Gemini audio response eksik speaker_id/text içeriyor.")
        start_sec = item.start_sec if item.start_sec is not None else cursor
        end_sec = item.end_sec if item.end_sec is not None else start_sec + max(1.0, len(text.split()) * 0.35)
        if end_sec < start_sec:
            raise AudioProviderRuntimeError("Gemini audio response geçersiz zaman aralığı içeriyor.")
        words = _words_for_text(text, start_sec, end_sec)
        utterances.append(
            Utterance(
                speaker_id=speaker_id,
                text=text,
                start_sec=round(start_sec, 2),
                end_sec=round(end_sec, 2),
                words=words,
            )
        )
        cursor = end_sec + 0.2

    return SpeakerLabelledTranscript(session_id=expected_session_id, utterances=utterances)


def _loads_json_object(text: str) -> dict[str, Any]:
    stripped = _strip_json_fences(text).strip()
    if not stripped:
        raise json.JSONDecodeError("empty response", text, 0)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise AudioProviderRuntimeError("Gemini audio provider JSON obje döndürmedi.")
    return payload


def _normalize_speaker_id(raw_speaker_id: str, speaker_map: dict[str, str]) -> str:
    raw = raw_speaker_id.strip()
    normalized = raw.upper()
    if len(normalized) == 1 and "A" <= normalized <= "Z":
        return normalized

    lowered = raw.lower()
    if lowered in {"speaker a", "konuşmacı a", "konusmaci a"}:
        return "A"
    if lowered in {"speaker b", "konuşmacı b", "konusmaci b"}:
        return "B"
    if lowered in {"speaker c", "konuşmacı c", "konusmaci c"}:
        return "C"

    if any(token in lowered for token in ("hekim", "doktor", "dentist", "clinician")):
        return "A"
    if any(token in lowered for token in ("hasta", "patient")):
        return "B"
    if any(token in lowered for token in ("asistan", "assistant", "hemşire", "hemsire")):
        return "C"

    key = lowered or raw
    if key not in speaker_map:
        speaker_map[key] = chr(ord("A") + len(speaker_map))
    return speaker_map[key]


def _audio_transcript_prompt() -> str:
    return """
You are a Turkish dental conversation transcription system.

Return JSON only:
{
  "utterances": [
    {"speaker_id": "A", "text": "...", "start_sec": 0.0, "end_sec": 2.4}
  ]
}

Rules:
- Transcribe Turkish speech faithfully.
- Split turns by speaker changes.
- Use neutral speaker labels A, B, C... Do not infer dentist/patient roles here.
- Preserve clinical uncertainty words such as şüpheli, olabilir, gerekebilir.
- Do not add clinical findings that are not spoken.
- If exact timestamps are uncertain, omit start_sec/end_sec; the app will approximate them.
- If only one person speaks, use speaker_id "A" for all utterances.
""".strip()


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


def _words_for_text(text: str, start_sec: float, end_sec: float) -> list[Word]:
    raw_words = text.split()
    if not raw_words:
        return []
    duration = max(0.05, (end_sec - start_sec) / len(raw_words))
    words = []
    cursor = start_sec
    for raw_word in raw_words:
        word_end = min(end_sec, cursor + duration)
        words.append(Word(text=raw_word, start_sec=round(cursor, 2), end_sec=round(word_end, 2)))
        cursor = word_end
    return words
