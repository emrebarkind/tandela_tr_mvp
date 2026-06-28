"""Manual golden-set eval for procedure extraction, code matching, checklist.

Run locally with a real Gemini key:
    cd backend && python -m evals.eval_golden_code_pipeline
"""

from __future__ import annotations

import traceback

from app.pipeline import stages
from app.pipeline.types import ChecklistItemStatus, CodeMatchState
from app.providers.gemini_provider import GeminiLLMProvider

from .golden_phase_a_common import (
    SCENARIOS,
    assert_expected_facts,
    assert_expected_procedures,
    extract_facts_for_phase_a,
    new_report,
    print_reports,
)


def _assert_expected_code_suggestions(report: dict, scenario: dict, facts, llm: GeminiLLMProvider) -> None:
    expected_bundles = scenario.get("expected_code_suggestions_after_role_approval")
    if expected_bundles is None:
        return

    try:
        procedures = stages.extract_procedures(facts)
        bundles = stages.match_codes_and_checklist(procedures, facts, llm)
    except Exception as exc:  # noqa: BLE001 - visible eval failure.
        report["error"] = f"code_pipeline {type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        return

    assert_expected_procedures(report, scenario, procedures)

    if len(bundles) != len(expected_bundles):
        report["mismatches"].append(
            f"code suggestion bundle sayısı: beklenen={len(expected_bundles)} gerçek={len(bundles)}"
        )

    for idx, expected in enumerate(expected_bundles):
        if idx >= len(bundles):
            report["mismatches"].append(f"expected code suggestion bundle eksik: index={idx} {expected!r}")
            continue

        bundle = bundles[idx]
        if len(bundle.candidates) == expected["candidate_count"]:
            report["matches"].append(f"code bundle {idx}: candidate_count == {expected['candidate_count']}")
        else:
            report["mismatches"].append(
                f"code bundle {idx} candidate_count: beklenen={expected['candidate_count']} gerçek={len(bundle.candidates)}"
            )

        candidate_codes = {candidate.code for candidate in bundle.candidates}
        explanation_codes = {explanation.code for explanation in bundle.explanations}
        if candidate_codes == explanation_codes:
            report["matches"].append(f"code bundle {idx}: explanations sadece candidate kodları açıkladı")
        else:
            report["mismatches"].append(
                f"code bundle {idx}: explanation code set uyuşmadı "
                f"candidates={sorted(candidate_codes)} explanations={sorted(explanation_codes)}"
            )

        actual_states = {result.match_state for result in bundle.match_results}
        expected_states = {CodeMatchState(value) for value in expected["match_states"]}
        if actual_states == expected_states:
            report["matches"].append(f"code bundle {idx}: match_states OK")
        else:
            report["mismatches"].append(
                f"code bundle {idx} match_states: beklenen={[s.value for s in expected_states]} "
                f"gerçek={[s.value for s in actual_states]}"
            )

        first_result = bundle.match_results[0] if bundle.match_results else None
        if first_result is None:
            if expected["checklist"]:
                report["mismatches"].append(f"code bundle {idx}: checklist bekleniyordu ama match_result yok")
            continue

        checklist_by_id = {item.item_id: item for item in first_result.checklist}
        for item_id, expected_status in expected["checklist"].items():
            actual = checklist_by_id.get(item_id)
            if actual is None:
                report["mismatches"].append(f"code bundle {idx}: checklist item yok: {item_id}")
                continue
            if actual.status == ChecklistItemStatus(expected_status):
                report["matches"].append(f"code bundle {idx}: checklist {item_id} == {expected_status}")
            else:
                report["mismatches"].append(
                    f"code bundle {idx}: checklist {item_id}: beklenen={expected_status} gerçek={actual.status.value}"
                )


def run_scenario(scenario: dict, llm: GeminiLLMProvider) -> dict:
    report = new_report(scenario)
    facts = extract_facts_for_phase_a(scenario, llm, report)
    if facts is None:
        return report

    assert_expected_facts(report, scenario, facts)
    _assert_expected_code_suggestions(report, scenario, facts, llm)
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
