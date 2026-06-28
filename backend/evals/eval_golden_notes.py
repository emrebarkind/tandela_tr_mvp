"""Manual golden-set eval for clinical_note_generation.

Run locally with a real Gemini key:
    cd backend && python -m evals.eval_golden_notes
"""

from __future__ import annotations

import traceback

from app.pipeline import stages
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
    if facts is None:
        return report

    assert_expected_facts(report, scenario, facts)
    try:
        note = stages.generate_clinical_note(facts, llm)
        stages._validate_note_against_facts(facts, note)
    except Exception as exc:  # noqa: BLE001 - visible eval failure.
        report["error"] = f"note {type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        return report

    section_counts = {
        "patient_complaint": len(note.patient_complaint),
        "history": len(note.history),
        "clinical_findings": len(note.clinical_findings),
        "assessment": len(note.assessment),
        "treatment_plan": len(note.treatment_plan),
        "procedures_note": len(note.procedures_note),
    }
    report["matches"].append(f"note: fact text/source_quote/source_role taşındı {section_counts}")
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
