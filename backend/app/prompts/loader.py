"""
Prompt dosyalarından (`backend/app/prompts/*.md`) system prompt çıkarma.

Kontrat: her prompt dosyası bir "## System / instruction" başlığından sonra
TEK bir fenced code block (```...```) içerir; o blok ham system prompt
metnidir (LLM'e gönderilecek talimat — Türkçe değil, İngilizce yazılmış
olabilir, önemli olan aynen, PARAFRAZE EDİLMEDEN gönderilmesidir). Beyin
katmanının üç aşaması da (role_assignment, clinical_facts_extraction,
clinical_note_generation — CLAUDE.md §3) bu kontrata uyacak şekilde yazılır.
"""

from __future__ import annotations

import re
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent

_SYSTEM_SECTION_RE = re.compile(
    r"##\s*System\s*/\s*instruction\s*\n+```[^\n]*\n(.*?)\n```",
    re.DOTALL,
)


def load_system_prompt(filename: str) -> str:
    """`backend/app/prompts/<filename>` içindeki system prompt bloğunu döner.

    Dosya yoksa ya da beklenen "## System / instruction" + fenced code block
    yapısı bulunamazsa hata fırlatır — sessizce boş/varsayılan bir prompt ile
    DEVAM ETMEZ. Bozuk bir prompt dosyasıyla LLM'i çağırıp sonucu yorumlamaya
    çalışmak, CLAUDE.md §4.1'in ("belirsizse tahmin etme") ruhuna aykırıdır:
    girdi bozuksa dur, sahte/varsayılan içerikle ilerleme.
    """
    path = _PROMPTS_DIR / filename
    text = path.read_text(encoding="utf-8")
    match = _SYSTEM_SECTION_RE.search(text)
    if match is None:
        raise ValueError(
            "Prompt dosyası beklenen formatta değil — '## System / instruction' "
            f"başlığı + fenced code block bulunamadı: {filename}"
        )
    return match.group(1).strip()
