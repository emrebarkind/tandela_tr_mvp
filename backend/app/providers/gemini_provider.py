"""
Gemini LLMProvider — role_assignment eval'i için (TEST AMAÇLI).

`LLMProvider` ABC'sinin (bkz. `providers/llm.py`) somut bir implementasyonu.
Amaç: golden-set.md senaryolarını gerçek modele gönderip role_assignment
prompt'unun tuzakları geçip geçmediğini ölçmek (eval, kontrat testi değil —
kontrat testleri `ScriptedLLM` ile `verify_*.py`/`verify_golden_set.py`'de
zaten yapılıyor).

KISIT NOTU (CLAUDE.md §5/§6): Bu eval TEST amaçlıdır, kısıt BİLİNÇLİ OLARAK
gevşek tutuldu. Gemini Developer API (api key) kullanılıyor — AB-region/DPA/
no-training garantisi YOK. PRODUCTION'da sağlık verisi için bu YETMEZ; somut
vendor seçimi hâlâ TBD (§10), production'da Vertex AI EU-region + DPA +
no-training şart. Bu dosyaya GERÇEK hasta verisi GÖNDERME — yalnızca
golden-set.md'deki simüle/sentetik transkriptlerle çalıştır.

Tasarım: bu sınıf "aptal" bir API sarmalayıcısıdır. Klinik mantık YOK,
fail-safe floor YOK, gate hesabı YOK — bunlar `stages.assign_roles`'ta yaşıyor
(kasıtlı: LLM çıktısına güvenmeyen post-processing katmanı orada, CLAUDE.md
§4.1). Bu sınıfın tek işi: prompt + transkript → model → ham metin (str).

Dönüş tipi kararı: `complete()` HAM JSON METNİNİ (str) döndürür — tıpkı
`ScriptedLLM.complete()` gibi. Parse (json.loads + Pydantic) TEK noktada,
`stages.assign_roles`'ta yapılır; malformed-JSON fail-safe'i de orada yaşar.
Bu provider asla dict/parsed nesne döndürmez.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

# Yeni, önerilen SDK: `pip install google-genai` (eski google-generativeai DEĞİL).
from google import genai
from google.genai import types

from app.providers.llm import LLMProvider

logger = logging.getLogger(__name__)

# Güncel model ID'si ai.google.dev/gemini-api/docs/models'tan teyit edilmeli.
# Flash sınıfı eval için yeterli ve ucuz (çok çağrı yapılacak). 2026 ortası
# itibarıyla gemini-2.0-flash KAPATILDI (Haziran 2026) — kullanma.
_DEFAULT_MODEL = "gemini-3.5-flash"

# Repo köküne göre .env yolu (backend/app/providers/gemini_provider.py'den 4 üst).
_ENV_FILE = os.path.join(os.path.dirname(__file__), "..", "..", ".env")


def _load_env_file(path: str) -> None:
    """Çok basit .env yükleyici — yeni bir bağımlılık (python-dotenv) eklemeden.

    Sadece `KEY=VALUE` satırlarını okur, `#` ile başlayan/boş satırları atlar,
    zaten ortamda set edilmiş bir değişkeni EZMEZ (gerçek env değişkeni her
    zaman önceliklidir). Dosya yoksa sessizce hiçbir şey yapmaz — eval
    script'inin GEMINI_API_KEY'i export ile de sağlaması desteklenir.
    """
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


class GeminiLLMProvider(LLMProvider):
    """role_assignment prompt'unu gerçek Gemini modeline gönderen provider."""

    def __init__(self, model: str = _DEFAULT_MODEL, api_key: Optional[str] = None) -> None:
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            _load_env_file(_ENV_FILE)
            key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY yok. backend/.env'e ekle (repo'ya commit etme — "
                ".gitignore'da) ya da ortam değişkeni olarak export et."
            )
        self._client = genai.Client(api_key=key)
        self._model = model

    @property
    def model(self) -> str:
        """Kullanılan model adı (debug/eval raporlama için — gizli bilgi taşımaz)."""
        return self._model

    def complete(self, system_prompt: str, user_input: str) -> str:
        """Modeli çağırır, HAM JSON METNİNİ (str) döndürür.

        `LLMProvider.complete()` ile birebir aynı imza/dönüş tipi (CLAUDE.md
        §6 — beynin üç aşaması da bu TEK arabirimi paylaşır).
        """
        # JSON modu: temiz JSON'a zorlar → ```json fence / preamble sorununu
        # büyük ölçüde ortadan kaldırır. temperature=0.0: sınıflandırma için
        # daha kararlı (rol ataması yaratıcılık değil, tutarlılık ister).
        #
        # DİKKAT: Gemini structured-output şeması Optional/Union tiplerini
        # desteklemiyor. `RoleAssignmentResult`'ta Optional alan var (`reason`)
        # — bu yüzden response_schema=RoleAssignmentResult VERİLMİYOR; sadece
        # response_mime_type="application/json" + prompt'un kendi "Output
        # JSON only" talimatı kullanılıyor.
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.0,
            response_mime_type="application/json",
        )

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user_input,
                config=config,
            )
        except Exception as exc:
            # Ağ/API hatası: SAHTE veri ÜRETME. Yükselt — assign_roles'un
            # "fail-safe'e düş" davranışı yalnızca PARSE edilebilir ama
            # sözleşmeyi bozan çıktılar için tasarlandı; API'nin kendisi
            # patladıysa bu görünür şekilde patlamalı (eval_golden_roles.py
            # senaryoyu "API error" olarak işaretler), sessizce yutulmaz.
            logger.error("gemini_api_error: model=%s error_type=%s", self._model, type(exc).__name__)
            raise

        text = response.text or ""
        return _strip_json_fences(text)

    def complete_structured(
        self, system_prompt: str, user_input: str, response_json_schema: dict[str, Any]
    ) -> str:
        """Call Gemini with server-side JSON schema enforcement."""
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.0,
            response_mime_type="application/json",
            response_json_schema=response_json_schema,
            max_output_tokens=8192,
        )
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user_input,
                config=config,
            )
        except Exception as exc:
            logger.error(
                "gemini_structured_api_error: model=%s error_type=%s",
                self._model,
                type(exc).__name__,
            )
            raise
        return _strip_json_fences(response.text or "")


def _strip_json_fences(text: str) -> str:
    """Model yine de ```json ... ``` ya da başına/sonuna metin koyarsa temizler.
    JSON modu açıkken çoğu zaman gereksiz ama zararsız savunma."""
    t = text.strip()
    if t.startswith("```"):
        parts = t.split("```", 2)
        t = parts[1] if len(parts) >= 2 else text
        if t.startswith("json"):
            t = t[len("json"):]
        t = t.strip().rstrip("`").strip()
    return t
