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

from abc import ABC, abstractmethod

from app.pipeline.types import AudioRef, SpeakerSegments, SpeakerLabelledTranscript, Transcript


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
