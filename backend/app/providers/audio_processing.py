"""
AudioProcessingProvider — vendor-agnostic ASR/diarization/alignment arabirimi.

CLAUDE.md §6 (kilitli): ASR/diarization backend'e doğrudan gömülmez.
V1: AB-region'lı entegre bulut API (tek çağrıda transcribe+diarize).
İleride self-host WhisperX + pyannote AYNI arabirimle takılır. Somut vendor
seçimi henüz TBD (bkz. CLAUDE.md §10) — bu dosya SADECE interface'i tanımlar,
hiçbir vendor SDK'sına bağımlılık içermez.

Pipeline kodu (bkz. pipeline/stages.py) hiçbir zaman vendor-specific bir
tipe/SDK'ya doğrudan referans vermez; her zaman bu arabirim üzerinden çalışır.
Veri kısıtları (AB-region, DPA, no-training, retention) her somut
implementasyon için geçerlidir — bu dosyada enforce edilmez, sözleşme olarak
burada belgelenir.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional

from app.pipeline.types import (
    AudioRef,
    SpeakerLabelledTranscript,
    SpeakerSegment,
    SpeakerSegments,
    Transcript,
    Utterance,
    Word,
)

_ENV_FILE = os.path.join(os.path.dirname(__file__), "..", "..", ".env")


def _load_env_file(path: str) -> None:
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


class AudioProcessingProvider(ABC):
    """ASR + diarization + alignment için vendor-agnostic arabirim.

    Somut implementasyonlar (örn. bulut API adapter'ı veya ileride
    WhisperX + pyannote self-host adapter'ı) bu sınıftan miras alır.
    Bu görev kapsamında SOMUT bir implementasyon YOK — vendor shootout
    build'in başında yapılır (CLAUDE.md §10).
    """

    @abstractmethod
    def transcribe(self, audio: AudioRef) -> Transcript:
        """Ham sesi word-level timestamp'li transkripte çevirir."""
        raise NotImplementedError

    @abstractmethod
    def diarize(self, audio: AudioRef) -> SpeakerSegments:
        """Sesi konuşmacı bazlı zaman segmentlerine ayırır (Speaker A/B/C)."""
        raise NotImplementedError

    @abstractmethod
    def align(
        self, transcript: Transcript, diarization: SpeakerSegments
    ) -> SpeakerLabelledTranscript:
        """Transkript kelimelerini diarization segmentleriyle hizalar."""
        raise NotImplementedError


class AudioProviderConfigurationError(RuntimeError):
    """Audio provider seçimi hatalı veya henüz desteklenmiyor."""


class AudioProviderRuntimeError(RuntimeError):
    """Audio provider çalışırken kontrollü biçimde yakalanabilecek hata."""


class NotConfiguredAudioProcessingProvider(AudioProcessingProvider):
    """Güvenli default: ses saklamaz, gerçek transkript üretmez."""

    def transcribe(self, audio: AudioRef) -> Transcript:
        raise NotImplementedError("Audio processing provider not configured.")

    def diarize(self, audio: AudioRef) -> SpeakerSegments:
        raise NotImplementedError("Audio processing provider not configured.")

    def align(self, transcript: Transcript, diarization: SpeakerSegments) -> SpeakerLabelledTranscript:
        raise NotImplementedError("Audio processing provider not configured.")


class DevFixtureAudioProcessingProvider(AudioProcessingProvider):
    """Lokal geliştirme provider'ı: gerçek sesi işlemez, sabit transcript üretir.

    Bu sınıf production için değildir. Amacı audio upload endpoint'inin
    `transcript_ready` yolunu, gerçek ASR vendor'ı seçilmeden test edebilmek.
    """

    _utterance_specs = [
        ("A", "Merhaba, şikayetiniz nedir?"),
        ("B", "Sağ alt tarafta iki gündür ağrım var, özellikle yemek yerken zonkluyor."),
        ("A", "Sağ alt altıda, yani 46 numarada derin çürük görüyorum."),
        ("C", "Hocam röntgeni açıyorum."),
        ("A", "Perküsyonda hassasiyet var. Kanal tedavisi gerekebilir."),
        ("A", "46 numara için kanal tedavisi planlandı, geçici restorasyon yapılacak."),
    ]

    def transcribe(self, audio: AudioRef) -> Transcript:
        return Transcript(session_id=audio.session_id, words=_fixture_words())

    def diarize(self, audio: AudioRef) -> SpeakerSegments:
        utterances = _fixture_utterances(audio.session_id)
        return SpeakerSegments(
            session_id=audio.session_id,
            segments=[
                SpeakerSegment(
                    speaker_id=utterance.speaker_id,
                    start_sec=utterance.start_sec,
                    end_sec=utterance.end_sec,
                )
                for utterance in utterances
            ],
        )

    def align(self, transcript: Transcript, diarization: SpeakerSegments) -> SpeakerLabelledTranscript:
        return SpeakerLabelledTranscript(
            session_id=transcript.session_id,
            utterances=_fixture_utterances(transcript.session_id),
        )


def create_audio_processing_provider(provider_name: Optional[str] = None) -> AudioProcessingProvider:
    """Env ile seçilen audio provider'ı oluşturur.

    `dev_fixture` yalnızca lokal geliştirme içindir; gerçek sesi işlemez.
    Gerçek ASR/diarization adapter'ı eklendiğinde route katmanı değişmeden
    buraya bağlanacak.
    """

    if provider_name is None:
        _load_env_file(_ENV_FILE)
    selected = (provider_name or os.environ.get("KLINIA_AUDIO_PROVIDER") or "not_configured").strip().lower()
    if selected in {"not_configured", "none", "disabled"}:
        return NotConfiguredAudioProcessingProvider()
    if selected in {"dev_fixture", "fixture", "dev"}:
        return DevFixtureAudioProcessingProvider()
    if selected in {"managed_http", "managed", "external_http"}:
        from app.providers.managed_audio_provider import ManagedHttpAudioProcessingProvider

        return ManagedHttpAudioProcessingProvider()
    if selected in {"gemini_audio", "gemini"}:
        from app.providers.gemini_audio_provider import GeminiAudioProcessingProvider

        return GeminiAudioProcessingProvider()
    if selected in {"deepgram", "deepgram_nova3", "deepgram_audio"}:
        from app.providers.deepgram_audio_provider import DeepgramAudioProcessingProvider

        return DeepgramAudioProcessingProvider()
    raise AudioProviderConfigurationError(f"Unsupported KLINIA_AUDIO_PROVIDER: {selected}")


def _fixture_utterances(session_id: str) -> list[Utterance]:
    utterances: list[Utterance] = []
    cursor = 0.0
    for speaker_id, text in DevFixtureAudioProcessingProvider._utterance_specs:
        words = _words_for_text(text, cursor)
        end_sec = words[-1].end_sec if words else cursor + 1.0
        utterances.append(
            Utterance(
                speaker_id=speaker_id,
                text=text,
                start_sec=cursor,
                end_sec=end_sec,
                words=words,
            )
        )
        cursor = end_sec + 0.35
    return utterances


def _fixture_words() -> list[Word]:
    words: list[Word] = []
    cursor = 0.0
    for _, text in DevFixtureAudioProcessingProvider._utterance_specs:
        utterance_words = _words_for_text(text, cursor)
        words.extend(utterance_words)
        cursor = (utterance_words[-1].end_sec if utterance_words else cursor + 1.0) + 0.35
    return words


def _words_for_text(text: str, start_sec: float) -> list[Word]:
    words: list[Word] = []
    cursor = start_sec
    for raw_word in text.split():
        end_sec = cursor + 0.22
        words.append(Word(text=raw_word, start_sec=round(cursor, 2), end_sec=round(end_sec, 2)))
        cursor = end_sec + 0.04
    return words
