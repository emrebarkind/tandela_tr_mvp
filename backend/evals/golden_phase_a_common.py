"""Shared helpers for manual Phase A golden-set evals.

These evals intentionally call the real Gemini provider and are not CI tests.
Run them manually after changing prompts or LLM pipeline stages.
"""

from __future__ import annotations

import traceback
from collections.abc import Iterable
from typing import Any

from app.pipeline import stages
from app.providers.gemini_provider import GeminiLLMProvider

from .eval_golden_roles import (
    SCENARIOS,
    _dentist_approved_roles,
    _fact_matches_expected,
    _fact_must_not_violations,
    _procedure_matches_expected,
    _t,
)


def new_report(scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": scenario["name"],
        "matches": [],
        "mismatches": [],
        "must_not_violations": [],
        "error": None,
    }


def get_role_labelled_transcript_for_phase_a(
    scenario: dict[str, Any],
    llm: GeminiLLMProvider,
    report: dict[str, Any],
):
    """Return role-labelled transcript after the review gate is handled for eval.

    For gate-blocking scenarios, this simulates the dentist approving the roles
    from docs/golden-set.md before downstream facts/note/procedure stages run.
    """
    transcript = _t(scenario["session_id"], scenario["lines"])

    try:
        role_result = stages.assign_roles(transcript, llm)
    except Exception as exc:  # noqa: BLE001 - eval should report, not hide.
        report["error"] = f"role {type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        return None

    if role_result.requires_role_review == scenario["expect_gate_blocks"]:
        report["matches"].append(f"role gate == {scenario['expect_gate_blocks']}")
    else:
        report["mismatches"].append(
            "role gate: beklenen={expected} gerçek={actual}".format(
                expected=scenario["expect_gate_blocks"],
                actual=role_result.requires_role_review,
            )
        )

    expected_facts = scenario.get("expected_facts_after_role_approval")
    if expected_facts is None:
        if role_result.requires_role_review:
            report["matches"].append("downstream: role gate bloklu senaryoda facts/note/procedure çalıştırılmadı")
        return None

    if role_result.requires_role_review:
        corrected = _dentist_approved_roles(scenario, transcript)
        report["matches"].append("role review: hekim onayı simüle edildi")
    else:
        corrected = role_result
        report["matches"].append("role review: gerekmedi")

    return stages.apply_dentist_role_correction(transcript, corrected)


def extract_facts_for_phase_a(
    scenario: dict[str, Any],
    llm: GeminiLLMProvider,
    report: dict[str, Any],
):
    role_labelled = get_role_labelled_transcript_for_phase_a(scenario, llm, report)
    if role_labelled is None:
        return None

    try:
        facts = stages.extract_clinical_facts(role_labelled, llm)
    except Exception as exc:  # noqa: BLE001 - visible eval failure.
        report["error"] = f"facts {type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        return None

    return facts


def assert_expected_facts(report: dict[str, Any], scenario: dict[str, Any], facts) -> None:
    expected_facts = scenario.get("expected_facts_after_role_approval")
    if expected_facts is None:
        return

    for expected in expected_facts:
        if any(_fact_matches_expected(fact, expected) for fact in facts.facts):
            report["matches"].append(
                "fact: {category}/{role}/{speaker}/fdi={fdi}/status={status}/uncertain={uncertain}".format(
                    category=expected["category"],
                    role=expected["source_role"],
                    speaker=expected["source_speaker"],
                    fdi=expected["tooth_number_fdi"],
                    status=expected["status"],
                    uncertain=expected["is_uncertain"],
                )
            )
        else:
            report["mismatches"].append(f"expected fact bulunamadı: {expected!r}")

    uncertain_text = "\n".join(facts.uncertain_items)
    for fragment in scenario.get("expected_uncertain_fragments", []):
        if fragment.lower() in uncertain_text.lower():
            report["matches"].append(f"uncertain_items contains {fragment!r}")
        else:
            report["mismatches"].append(f"uncertain_items içinde beklenen parça yok: {fragment!r}")

    for violation in _fact_must_not_violations(scenario, facts):
        report["must_not_violations"].append(violation)


def assert_expected_procedures(report: dict[str, Any], scenario: dict[str, Any], procedures) -> None:
    expected_procedures = scenario.get("expected_procedures_after_role_approval")
    if expected_procedures is None:
        return

    if len(procedures) != len(expected_procedures):
        report["mismatches"].append(
            f"procedure sayısı: beklenen={len(expected_procedures)} gerçek={len(procedures)} "
            f"çıktı={[p.model_dump() for p in procedures]!r}"
        )

    for expected in expected_procedures:
        if any(_procedure_matches_expected(procedure, expected) for procedure in procedures):
            report["matches"].append(
                "procedure: {family}/fdi={fdi}/status={status}/surface={surface}/canal={canal}".format(
                    family=expected["procedure_family"],
                    fdi=expected["tooth_number_fdi"],
                    status=expected["status"],
                    surface=expected["surface_count"],
                    canal=expected["canal_count"],
                )
            )
        else:
            report["mismatches"].append(f"expected procedure bulunamadı: {expected!r}")


def print_reports(reports: Iterable[dict[str, Any]]) -> int:
    any_failure = False
    for report in reports:
        print(f"\n--- {report['name']} ---")
        if report["error"]:
            print(f"  HATA: {report['error']}")
            if report.get("traceback"):
                print(report["traceback"])
            any_failure = True
            continue
        for message in report["matches"]:
            print(f"  OK: {message}")
        for message in report["mismatches"]:
            print(f"  MISMATCH: {message}")
            any_failure = True
        for violation in report["must_not_violations"]:
            print(f"  MUST NOT İHLALİ: {violation}")
            any_failure = True

    print("\nSONUÇ:", "mismatch/ihlal var" if any_failure else "tüm hedefler geçti")
    return 1 if any_failure else 0


__all__ = [
    "SCENARIOS",
    "assert_expected_facts",
    "assert_expected_procedures",
    "extract_facts_for_phase_a",
    "new_report",
    "print_reports",
]
