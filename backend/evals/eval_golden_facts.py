"""Manual golden-set eval for clinical_facts_extraction.

Run locally with a real Gemini key:
    cd backend && python -m evals.eval_golden_facts
"""

from __future__ import annotations

import json
import os

from app.pipeline import stages
from app.pipeline.types import ClinicalFactsBundle
from app.providers.gemini_provider import GeminiLLMProvider

from .golden_phase_a_common import (
    SCENARIOS,
    assert_expected_facts,
    extract_facts_for_phase_a,
    get_role_labelled_transcript_for_phase_a,
    new_report,
    print_reports,
)


S5_RAW_FACTS_FROM_DEBUG = {
    "session_id": "golden-s5",
    "facts": [
        {
            "category": "patient_complaint",
            "text": "Sol üst tarafta yaklaşık bir haftadır ağrı var, özellikle sıcak yiyecek yiyince artıyor.",
            "source_quote": "Sol üst tarafta yaklaşık bir haftadır ağrı var, özellikle sıcak yiyecek yiyince artıyor.",
            "source_role": "patient",
            "source_speaker": "B",
            "tooth_number_fdi": None,
            "status": None,
            "is_uncertain": False,
        },
        {
            "category": "clinical_findings",
            "text": "Sol üst yedi numarada gingival kenara yakın derin çürük var.",
            "source_quote": "Sol üst yedi numarada derin çürük görüyorum, gingival kenara yakın.",
            "source_role": "dentist",
            "source_speaker": "A",
            "tooth_number_fdi": 27,
            "status": None,
            "is_uncertain": False,
        },
        {
            "category": "clinical_findings",
            "text": "Röntgende pulpaya yakın şüpheli bir görüntü var.",
            "source_quote": "Röntgende pulpaya yakın bir görüntü var, kesin olarak söylemek zor ama kanal tedavisi gerekebilir.",
            "source_role": "dentist",
            "source_speaker": "A",
            "tooth_number_fdi": 27,
            "status": None,
            "is_uncertain": True,
        },
        {
            "category": "assessment",
            "text": "Kanal tedavisi gerekebilir.",
            "source_quote": "Röntgende pulpaya yakın bir görüntü var, kesin olarak söylemek zor ama kanal tedavisi gerekebilir.",
            "source_role": "dentist",
            "source_speaker": "A",
            "tooth_number_fdi": 27,
            "status": None,
            "is_uncertain": True,
        },
        {
            "category": "patient_complaint",
            "text": "Dişin çekilmesi gerekip gerekmeyeceğine dair endişe.",
            "source_quote": "Yani dişimi çekmeniz gerekmeyecek değil mi?",
            "source_role": "patient",
            "source_speaker": "B",
            "tooth_number_fdi": 27,
            "status": None,
            "is_uncertain": False,
        },
        {
            "category": "treatment_plan",
            "text": "Şu an çekim düşünülmüyor, önce kanal tedavisi denenecek, başarısız olursa değerlendirilecek.",
            "source_quote": "Hayır, şu an çekim düşünmüyoruz. Önce kanal tedavisini deneyelim, başarısız olursa değerlendiririz.",
            "source_role": "dentist",
            "source_speaker": "A",
            "tooth_number_fdi": 27,
            "status": None,
            "is_uncertain": False,
        },
        {
            "category": "patient_complaint",
            "text": "Sağ tarafta hafif bir hassasiyet var.",
            "source_quote": "Peki sağ tarafımda da hafif bir hassasiyet var, geçen ay kompozit dolgu yaptırmıştım oradan.",
            "source_role": "patient",
            "source_speaker": "B",
            "tooth_number_fdi": None,
            "status": None,
            "is_uncertain": False,
        },
        {
            "category": "history",
            "text": "Geçen ay sağ taraftan kompozit dolgu yaptırılmış.",
            "source_quote": "Peki sağ tarafımda da hafif bir hassasiyet var, geçen ay kompozit dolgu yaptırmıştım oradan.",
            "source_role": "patient",
            "source_speaker": "B",
            "tooth_number_fdi": None,
            "status": None,
            "is_uncertain": False,
        },
        {
            "category": "clinical_findings",
            "text": "Sağ üst altı numarada iki yüzlü kompozit dolgu var, aşınma yok gibi görünüyor.",
            "source_quote": "Sağ üst altı numarada iki yüzlü kompozit dolgu var, aşınma yok gibi görünüyor, şimdilik bir işlem gerekmiyor, takip edelim.",
            "source_role": "dentist",
            "source_speaker": "A",
            "tooth_number_fdi": 16,
            "status": None,
            "is_uncertain": False,
        },
        {
            "category": "treatment_plan",
            "text": "Şimdilik bir işlem gerekmiyor, takip edilecek.",
            "source_quote": "Sağ üst altı numarada iki yüzlü kompozit dolgu var, aşınma yok gibi görünüyor, şimdilik bir işlem gerekmiyor, takip edelim.",
            "source_role": "dentist",
            "source_speaker": "A",
            "tooth_number_fdi": 16,
            "status": None,
            "is_uncertain": False,
        },
        {
            "category": "procedures",
            "text": "Sol üst yedi numara için kanal tedavisi planlandı.",
            "source_quote": "Sol üst yedi numara için kanal tedavisi planlandı, bugün geçici dolgu yapıldı.",
            "source_role": "dentist",
            "source_speaker": "A",
            "tooth_number_fdi": 27,
            "status": "planned",
            "is_uncertain": False,
        },
        {
            "category": "treatment_plan",
            "text": "Sol üst yedi numara için kanal tedavisi planlandı.",
            "source_quote": "Sol üst yedi numara için kanal tedavisi planlandı, bugün geçici dolgu yapıldı.",
            "source_role": "dentist",
            "source_speaker": "A",
            "tooth_number_fdi": 27,
            "status": "planned",
            "is_uncertain": False,
        },
        {
            "category": "procedures",
            "text": "Sol üst yedi numaraya bugün geçici dolgu yapıldı.",
            "source_quote": "Sol üst yedi numara için kanal tedavisi planlandı, bugün geçici dolgu yapıldı.",
            "source_role": "dentist",
            "source_speaker": "A",
            "tooth_number_fdi": 27,
            "status": "performed",
            "is_uncertain": False,
        },
    ],
    "uncertain_items": [
        "Sağ üst altı numaradaki iki yüzlü kompozit dolgunun hangi yüzeylerde olduğu belirtilmemiştir."
    ],
}


def _debug_raw_facts_call_s1(llm: GeminiLLMProvider) -> None:
    """DEBUG-ONLY: S1 clinical_facts_extraction ham LLM çıktısını basar."""
    s1 = SCENARIOS[0]
    assert s1["name"] == "S1"
    report = new_report(s1)
    role_labelled = get_role_labelled_transcript_for_phase_a(s1, llm, report)

    print("=" * 70)
    print("DEBUG (S1) — clinical_facts_extraction fail-safe'den ÖNCE ham LLM çıktısı")
    print(f"  model: {llm.model}")
    print("-" * 70)

    if role_labelled is None:
        print("  S1 role-labelled transcript hazırlanamadı; facts raw call atlandı.")
        if report["error"]:
            print(f"  role hazırlık hatası: {report['error']}")
        for mismatch in report["mismatches"]:
            print(f"  role hazırlık mismatch: {mismatch}")
        print("=" * 70)
        return

    system_prompt = stages.load_system_prompt(stages.CLINICAL_FACTS_PROMPT_FILE)
    user_input = stages._build_clinical_facts_user_input(role_labelled)

    try:
        raw = llm.complete(system_prompt, user_input)
    except Exception as exc:  # noqa: BLE001 - teşhis amaçlı görünür çıktı.
        print(f"  complete() EXCEPTION fırlattı: {type(exc).__name__}: {exc}")
        cause = exc.__cause__
        if cause is not None:
            print(f"    __cause__: {type(cause).__name__}: {cause}")
        print("=" * 70)
        return

    if raw == "":
        print("  complete() BOŞ STRING döndürdü.")
        print("=" * 70)
        return

    print(f"  HAM STRING ({len(raw)} karakter):")
    print(f"    {raw!r}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"  JSON PARSE HATASI (geçersiz JSON): {exc}")
        print("=" * 70)
        return

    print("  JSON parse OK. Parsed içerik:")
    print(f"    {data!r}")
    missing = [key for key in ("facts", "uncertain_items") if key not in data]
    if missing:
        print(f"  Geçerli JSON ama BEKLENEN ÜST SEVİYE ALANLAR EKSİK: {missing}")
    print("=" * 70)


def _debug_raw_facts_call_scenario(llm: GeminiLLMProvider, scenario_name: str) -> None:
    """DEBUG-ONLY: seçilen senaryo için clinical_facts_extraction ham LLM çıktısını basar."""
    scenario = next((item for item in SCENARIOS if item["name"] == scenario_name), None)
    if scenario is None:
        print(f"DEBUG: {scenario_name!r} senaryosu bulunamadı.")
        return

    report = new_report(scenario)
    role_labelled = get_role_labelled_transcript_for_phase_a(scenario, llm, report)

    print("=" * 70)
    print(f"DEBUG ({scenario_name}) — clinical_facts_extraction fail-safe'den ÖNCE ham LLM çıktısı")
    print(f"  model: {llm.model}")
    print("-" * 70)

    if role_labelled is None:
        print(f"  {scenario_name} role-labelled transcript hazırlanamadı; facts raw call atlandı.")
        if report["error"]:
            print(f"  role hazırlık hatası: {report['error']}")
        for mismatch in report["mismatches"]:
            print(f"  role hazırlık mismatch: {mismatch}")
        print("=" * 70)
        return

    system_prompt = stages.load_system_prompt(stages.CLINICAL_FACTS_PROMPT_FILE)
    user_input = stages._build_clinical_facts_user_input(role_labelled)

    try:
        raw = llm.complete(system_prompt, user_input)
    except Exception as exc:  # noqa: BLE001 - teşhis amaçlı görünür çıktı.
        print(f"  complete() EXCEPTION fırlattı: {type(exc).__name__}: {exc}")
        cause = exc.__cause__
        if cause is not None:
            print(f"    __cause__: {type(cause).__name__}: {cause}")
        print("=" * 70)
        return

    if raw == "":
        print("  complete() BOŞ STRING döndürdü.")
        print("=" * 70)
        return

    print(f"  HAM STRING ({len(raw)} karakter):")
    print(raw)
    print("=" * 70)


def _debug_raw_note_call_s5(llm: GeminiLLMProvider) -> None:
    """DEBUG-ONLY: S5 facts JSON'u ile clinical_note_generation ham LLM çıktısını basar."""
    facts = ClinicalFactsBundle.model_validate(S5_RAW_FACTS_FROM_DEBUG)
    safe_facts = stages._enforce_source_role_invariant(facts)
    system_prompt = stages.load_system_prompt(stages.CLINICAL_NOTE_PROMPT_FILE)
    user_input = stages._build_clinical_note_user_input(safe_facts)

    print("=" * 70)
    print("DEBUG (S5) — clinical_note_generation fail-safe'den ÖNCE ham LLM çıktısı")
    print(f"  model: {llm.model}")
    print("-" * 70)
    print("  INPUT FACTS JSON:")
    print(safe_facts.model_dump_json(exclude_none=False, indent=2))
    print("-" * 70)

    try:
        raw = llm.complete(system_prompt, user_input)
    except Exception as exc:  # noqa: BLE001 - teşhis amaçlı görünür çıktı.
        print(f"  complete() EXCEPTION fırlattı: {type(exc).__name__}: {exc}")
        cause = exc.__cause__
        if cause is not None:
            print(f"    __cause__: {type(cause).__name__}: {cause}")
        print("=" * 70)
        return

    if raw == "":
        print("  complete() BOŞ STRING döndürdü.")
        print("=" * 70)
        return

    print(f"  HAM STRING ({len(raw)} karakter):")
    print(raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"  JSON PARSE HATASI (geçersiz JSON): {exc}")
        print("=" * 70)
        return

    print("-" * 70)
    print("  SOURCE_QUOTE KARŞILAŞTIRMA:")
    input_quotes = {fact.source_quote for fact in safe_facts.facts}
    for section in (
        "patient_complaint",
        "history",
        "clinical_findings",
        "assessment",
        "treatment_plan",
        "procedures_note",
    ):
        for item in data.get(section, []):
            quote = item.get("source_quote") if isinstance(item, dict) else None
            status = "OK" if quote in input_quotes else "DEĞİŞMİŞ/YOK"
            print(f"    {section}: {status}: {quote!r}")
    print("=" * 70)


def run_scenario(scenario: dict, llm: GeminiLLMProvider) -> dict:
    report = new_report(scenario)
    facts = extract_facts_for_phase_a(scenario, llm, report)
    if facts is not None:
        assert_expected_facts(report, scenario, facts)
    return report


def main() -> int:
    try:
        llm = GeminiLLMProvider()
    except RuntimeError as exc:
        print(f"DURDU: {exc}")
        return 2

    debug_scenario = os.environ.get("DEBUG_GOLDEN_FACTS_SCENARIO")
    if debug_scenario:
        _debug_raw_facts_call_scenario(llm, debug_scenario)
        return 0

    debug_note_scenario = os.environ.get("DEBUG_GOLDEN_NOTE_SCENARIO")
    if debug_note_scenario == "S5":
        _debug_raw_note_call_s5(llm)
        return 0

    _debug_raw_facts_call_s1(llm)

    return print_reports(run_scenario(scenario, llm) for scenario in SCENARIOS)


if __name__ == "__main__":
    raise SystemExit(main())
