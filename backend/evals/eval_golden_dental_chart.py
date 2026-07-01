"""Manual golden-set eval for dental chart procedure enrichment.

Run locally with a real Gemini key:
    cd backend && python -m evals.eval_golden_dental_chart
"""

from __future__ import annotations

import traceback

from app.pipeline import stages
from app.pipeline.types import DentalCondition
from app.providers.gemini_provider import GeminiLLMProvider

from .golden_phase_a_common import (
    SCENARIOS,
    extract_facts_for_phase_a,
    new_report,
    print_reports,
)


def _assert_s1_dental_chart(report: dict, procedures) -> None:
    matches = [
        procedure
        for procedure in procedures
        if procedure.tooth_number_fdi == 46
        and procedure.procedure_family == "kanal_tedavisi"
        and procedure.condition == DentalCondition.RCT
    ]
    if matches:
        report["matches"].append("dental chart S1: 46 kanal_tedavisi -> condition=rct")
    else:
        report["mismatches"].append(
            "dental chart S1: 46 kanal_tedavisi için condition=rct bulunamadı; "
            f"çıktı={[p.model_dump(mode='json') for p in procedures]!r}"
        )


def run_scenario(scenario: dict, llm: GeminiLLMProvider) -> dict:
    report = new_report(scenario)
    facts = extract_facts_for_phase_a(scenario, llm, report)
    if facts is None:
        return report

    try:
        procedures = stages.extract_dental_chart_commands(facts, llm)
    except Exception as exc:  # noqa: BLE001 - visible eval failure.
        report["error"] = f"dental_chart {type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        return report

    if scenario["name"] == "S1":
        _assert_s1_dental_chart(report, procedures)
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
