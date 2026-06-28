"""Manual golden-set eval for clinical_facts_extraction.

Run locally with a real Gemini key:
    cd backend && python -m evals.eval_golden_facts
"""

from __future__ import annotations

from app.providers.gemini_provider import GeminiLLMProvider

from .golden_phase_a_common import (
    SCENARIOS,
    assert_expected_facts,
    extract_facts_for_phase_a,
    new_report,
    print_reports,
)


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

    return print_reports(run_scenario(scenario, llm) for scenario in SCENARIOS)


if __name__ == "__main__":
    raise SystemExit(main())
