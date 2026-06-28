"""
Vendor-agnostic LLM çağrı arabirimi (CLAUDE.md §6, §10).

CLAUDE.md §6: "LLM çağrıları da aynı veri kısıtlarına (AB/DPA/no-training)
tabidir." §10: "LLM modeli: beyin için somut model seçmedim; §6 kısıtlarına
uyan herhangi biri. Karar senin." — bu yüzden somut vendor burada YOK, sadece
arabirim (tıpkı `providers/audio_processing.py`'deki `AudioProcessingProvider`
gibi).

Beyin katmanının ÜÇ aşaması da (role_assignment, clinical_facts_extraction,
clinical_note_generation — CLAUDE.md §3) bu TEK arabirimi paylaşır: prompt
dosyası ve çıktının parse edilme şekli aşamaya göre değişir, ama "sistem
talimatı + kullanıcı girdisi ver, ham metin al" çağrı şekli her zaman aynıdır.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Somut implementasyon (vendor seçimi §10'da TBD) bu arabirimi uygular.

    KVKK (CLAUDE.md §5): somut implementasyon AB-region/DPA/no-training
    kısıtlarına uymalı; gönderilen metin (transkript/fact JSON) model
    eğitimi için kullanılmaz, kalıcı saklanmaz.
    """

    @abstractmethod
    def complete(self, system_prompt: str, user_input: str) -> str:
        """Sistem talimatı + kullanıcı girdisiyle LLM'i çağırır, ham metin
        çıktısını döner.

        Çıktının parse edilmesi (örn. JSON → Pydantic) bu arabirimin
        SORUMLULUĞUNDA DEĞİLDİR — bu yalnızca ham tamamlamayı döner.
        Çağıran taraf (örn. `stages.assign_roles`) çıktıyı doğrular; bozuk/
        sözleşmeye uymayan çıktı asla sessizce "iyimser" bir sonuca
        dönüştürülmez (CLAUDE.md §4.1 — belirsizse tahmin etme, bu kural
        LLM çıktısının doğrulanmasına da uygulanır).
        """
        raise NotImplementedError
