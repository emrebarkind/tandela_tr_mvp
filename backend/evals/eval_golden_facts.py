"""Manual golden-set eval for clinical_facts_extraction.

Run locally with a real Gemini key:
    cd backend && python -m evals.eval_golden_facts
"""

from __future__ import annotations

import json

from app.pipeline import stages
from app.providers.gemini_provider import GeminiLLMProvider

from .golden_phase_a_common import (
    SCENARIOS,
    assert_expected_facts,
    extract_facts_for_phase_a,
    get_role_labelled_transcript_for_phase_a,
    new_report,
    print_reports,
)


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

    _debug_raw_facts_call_s1(llm)

    return print_reports(run_scenario(scenario, llm) for scenario in SCENARIOS)


if __name__ == "__main__":
    raise SystemExit(main())
