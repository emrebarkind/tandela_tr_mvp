"""Deterministik code matching + checklist + opsiyonel LLM açıklama katmanı.

Bu modül, kapalı/versiyonlanmış kod kaynağı sınırını temsil eder. Şimdilik
gerçek TDB/SUT verisi yerine küçük bir fixture DB kullanır; LLM yalnızca mevcut
adayları açıklayabilir, aday kod ekleyemez/seçemez/değiştiremez.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from app.pipeline.types import (
    CandidateCode,
    CanalCount,
    ChecklistItemResult,
    ChecklistItemStatus,
    ClinicalFactsBundle,
    CodeExplanation,
    CodeMatchResult,
    CodeMatchState,
    CodeSuggestionBundle,
    DentistRole,
    FactCategory,
    ProcedureObject,
    ProcedureStatus,
    SurfaceCount,
)
from app.prompts.loader import load_system_prompt
from app.providers.llm import LLMProvider

logger = logging.getLogger(__name__)

CODE_EXPLANATION_PROMPT_FILE = "code_explanation.md"

_CODE_FIXTURE_SOURCE = "Fixture placeholder - real TDB/SUT code source TBD"
_CODE_FIXTURE_VERSION = "fixture-v1"

_CODE_DB_FIXTURE = [
    {
        "code": "FIX-KOMPOZIT-1Y",
        "procedure_name": "Kompozit Dolgu (Tek Yüzlü)",
        "category": "Tedavi ve Endodonti",
        "match_keys": {"procedure_family": "kompozit_dolgu", "surface_count": SurfaceCount.ONE_SURFACE},
        "required_documentation": [
            {"item_id": "tooth_number", "label": "Diş numarası (FDI)", "severity": "required"},
            {"item_id": "surface_name", "label": "Yüzey ismi", "severity": "required"},
            {"item_id": "indication", "label": "Gerekçe (çürük vb.)", "severity": "required"},
            {"item_id": "material", "label": "Kullanılan materyal", "severity": "recommended"},
            {"item_id": "status", "label": "İşlem durumu", "severity": "required"},
        ],
    },
    {
        "code": "FIX-KOMPOZIT-2Y",
        "procedure_name": "Kompozit Dolgu (İki Yüzlü)",
        "category": "Tedavi ve Endodonti",
        "match_keys": {"procedure_family": "kompozit_dolgu", "surface_count": SurfaceCount.TWO_SURFACE},
        "required_documentation": [
            {"item_id": "tooth_number", "label": "Diş numarası (FDI)", "severity": "required"},
            {"item_id": "surface_names", "label": "İki yüzeyin ismi", "severity": "required"},
            {"item_id": "indication", "label": "Gerekçe (çürük vb.)", "severity": "required"},
            {"item_id": "material", "label": "Kullanılan materyal", "severity": "recommended"},
            {"item_id": "status", "label": "İşlem durumu", "severity": "required"},
        ],
    },
    {
        "code": "FIX-KOMPOZIT-3Y",
        "procedure_name": "Kompozit Dolgu (Üç Yüzlü)",
        "category": "Tedavi ve Endodonti",
        "match_keys": {"procedure_family": "kompozit_dolgu", "surface_count": SurfaceCount.THREE_SURFACE},
        "required_documentation": [
            {"item_id": "tooth_number", "label": "Diş numarası (FDI)", "severity": "required"},
            {"item_id": "surface_names", "label": "Üç yüzeyin ismi", "severity": "required"},
            {"item_id": "indication", "label": "Gerekçe (çürük vb.)", "severity": "required"},
            {"item_id": "material", "label": "Kullanılan materyal", "severity": "recommended"},
            {"item_id": "status", "label": "İşlem durumu", "severity": "required"},
        ],
    },
    {
        "code": "FIX-KANAL-1K",
        "procedure_name": "Kanal Tedavisi (Tek Kanal)",
        "category": "Tedavi ve Endodonti",
        "match_keys": {"procedure_family": "kanal_tedavisi", "canal_count": CanalCount.ONE_CANAL},
        "required_documentation": [
            {"item_id": "tooth_number", "label": "Diş numarası (FDI)", "severity": "required"},
            {"item_id": "canal_count", "label": "Kanal sayısı", "severity": "required"},
            {"item_id": "endo_diagnosis", "label": "Endodontik tanı/gerekçe", "severity": "required"},
            {"item_id": "radiograph", "label": "Röntgen bulgusu", "severity": "recommended"},
            {"item_id": "status", "label": "İşlem durumu", "severity": "required"},
        ],
    },
    {
        "code": "FIX-KANAL-2K",
        "procedure_name": "Kanal Tedavisi (İki Kanal)",
        "category": "Tedavi ve Endodonti",
        "match_keys": {"procedure_family": "kanal_tedavisi", "canal_count": CanalCount.TWO_CANAL},
        "required_documentation": [
            {"item_id": "tooth_number", "label": "Diş numarası (FDI)", "severity": "required"},
            {"item_id": "canal_count", "label": "Kanal sayısı", "severity": "required"},
            {"item_id": "endo_diagnosis", "label": "Endodontik tanı/gerekçe", "severity": "required"},
            {"item_id": "radiograph", "label": "Röntgen bulgusu", "severity": "recommended"},
            {"item_id": "status", "label": "İşlem durumu", "severity": "required"},
        ],
    },
    {
        "code": "FIX-KANAL-3K",
        "procedure_name": "Kanal Tedavisi (Üç Kanal)",
        "category": "Tedavi ve Endodonti",
        "match_keys": {"procedure_family": "kanal_tedavisi", "canal_count": CanalCount.THREE_CANAL},
        "required_documentation": [
            {"item_id": "tooth_number", "label": "Diş numarası (FDI)", "severity": "required"},
            {"item_id": "canal_count", "label": "Kanal sayısı", "severity": "required"},
            {"item_id": "endo_diagnosis", "label": "Endodontik tanı/gerekçe", "severity": "required"},
            {"item_id": "radiograph", "label": "Röntgen bulgusu", "severity": "recommended"},
            {"item_id": "status", "label": "İşlem durumu", "severity": "required"},
        ],
    },
    {
        "code": "FIX-GECICI-REST",
        "procedure_name": "Geçici Restorasyon",
        "category": "Tedavi ve Endodonti",
        "match_keys": {"procedure_family": "gecici_restorasyon"},
        "required_documentation": [
            {"item_id": "tooth_number", "label": "Diş numarası (FDI)", "severity": "required"},
            {"item_id": "status", "label": "İşlem durumu", "severity": "required"},
        ],
    },
]


def match_codes_and_checklist(
    procedures: list[ProcedureObject],
    facts: Optional[ClinicalFactsBundle] = None,
    llm: Optional[LLMProvider] = None,
) -> list[CodeSuggestionBundle]:
    """Aday kodları kapalı fixture DB'den bul, checklist üret, açıklamayı kilitle.

    `facts` pipeline katmanında source-role invariant'ından geçirilmiş olmalıdır.
    Bu modül yine de checklist kanıtı ararken sadece `dentist` kaynaklı fact'leri
    kullanır.
    """
    bundles: list[CodeSuggestionBundle] = []

    for procedure in procedures:
        candidates = _find_candidate_records(procedure)
        candidate_codes = [_candidate_from_record(record) for record in candidates]

        match_results: list[CodeMatchResult] = []
        for record in candidates:
            checklist = _evaluate_checklist(procedure, facts, record)
            match_results.append(
                CodeMatchResult(
                    code=record["code"],
                    checklist=checklist,
                    match_state=_determine_match_state(len(candidates), checklist),
                )
            )

        ambiguity_note = _ambiguity_note(procedure, candidates)
        dentist_must_choose = len(candidates) != 1 or any(
            r.match_state != CodeMatchState.CONFIRMED_BY_DOCUMENTATION for r in match_results
        )
        explanations = (
            _generate_code_explanations(
                procedure=procedure,
                candidates=candidate_codes,
                match_results=match_results,
                ambiguity_note=ambiguity_note,
                dentist_must_choose=dentist_must_choose,
                llm=llm,
            )
            if llm is not None and candidate_codes
            else []
        )

        bundles.append(
            CodeSuggestionBundle(
                session_id=facts.session_id if facts is not None else "",
                candidates=candidate_codes,
                match_results=match_results,
                explanations=explanations,
                ambiguity_note=ambiguity_note,
                dentist_must_choose=dentist_must_choose,
            )
        )

    return bundles


def _generate_code_explanations(
    procedure: ProcedureObject,
    candidates: list[CandidateCode],
    match_results: list[CodeMatchResult],
    ambiguity_note: Optional[str],
    dentist_must_choose: bool,
    llm: LLMProvider,
) -> list[CodeExplanation]:
    system_prompt = load_system_prompt(CODE_EXPLANATION_PROMPT_FILE)
    user_input = _build_code_explanation_user_input(
        procedure=procedure,
        candidates=candidates,
        match_results=match_results,
        ambiguity_note=ambiguity_note,
        dentist_must_choose=dentist_must_choose,
    )

    try:
        raw_output = llm.complete(system_prompt, user_input)
        data = _loads_llm_json_object(raw_output)
        explanations = _normalize_code_explanation_payload(data)
        _validate_code_explanations(candidates, explanations)
        return explanations
    except Exception:
        logger.error(
            "code_explanation_llm_output_invalid: procedure_family=%s — explanations boş bırakılıyor.",
            procedure.procedure_family,
        )
        return []


def _build_code_explanation_user_input(
    procedure: ProcedureObject,
    candidates: list[CandidateCode],
    match_results: list[CodeMatchResult],
    ambiguity_note: Optional[str],
    dentist_must_choose: bool,
) -> str:
    payload = {
        "procedure_object": procedure.model_dump(mode="json"),
        "candidate_codes": [candidate.model_dump(mode="json") for candidate in candidates],
        "match_results": [result.model_dump(mode="json") for result in match_results],
        "deterministic_ambiguity_note": ambiguity_note,
        "deterministic_dentist_must_choose": dentist_must_choose,
    }
    return json.dumps(payload, ensure_ascii=False)


def _normalize_code_explanation_payload(data: object) -> list[CodeExplanation]:
    if not isinstance(data, dict):
        raise ValueError("code explanation payload dict değil")
    explanations_field = _first_present(data, ("explanations", "code_explanations"))
    if not isinstance(explanations_field, list):
        raise ValueError("code explanations list değil")
    return [CodeExplanation.model_validate(item) for item in explanations_field]


def _validate_code_explanations(
    candidates: list[CandidateCode], explanations: list[CodeExplanation]
) -> None:
    candidate_codes = [candidate.code for candidate in candidates]
    explanation_codes = [explanation.code for explanation in explanations]
    if sorted(explanation_codes) != sorted(candidate_codes):
        raise ValueError("explanation code set candidate set ile eşleşmedi")
    if len(explanation_codes) != len(set(explanation_codes)):
        raise ValueError("duplicate explanation code")
    for explanation in explanations:
        if not explanation.fit_reason.strip():
            raise ValueError("fit_reason boş olamaz")


def _find_candidate_records(procedure: ProcedureObject) -> list[dict]:
    family_records = [
        record
        for record in _CODE_DB_FIXTURE
        if record["match_keys"]["procedure_family"] == procedure.procedure_family
    ]

    candidates = [
        record
        for record in family_records
        if _record_matches_procedure(record, procedure)
    ]

    if candidates:
        return candidates

    if procedure.surface_count == SurfaceCount.UNCLEAR:
        return family_records
    if procedure.canal_count == CanalCount.UNCLEAR:
        return family_records
    return []


def _record_matches_procedure(record: dict, procedure: ProcedureObject) -> bool:
    match_keys = record["match_keys"]
    if match_keys["procedure_family"] != procedure.procedure_family:
        return False
    if "surface_count" in match_keys and procedure.surface_count != match_keys["surface_count"]:
        return False
    if "canal_count" in match_keys and procedure.canal_count != match_keys["canal_count"]:
        return False
    return True


def _candidate_from_record(record: dict) -> CandidateCode:
    return CandidateCode(
        code=record["code"],
        procedure_name=record["procedure_name"],
        category=record["category"],
        source=_CODE_FIXTURE_SOURCE,
        source_version=_CODE_FIXTURE_VERSION,
    )


def _evaluate_checklist(
    procedure: ProcedureObject, facts: Optional[ClinicalFactsBundle], record: dict
) -> list[ChecklistItemResult]:
    return [
        _evaluate_checklist_item(procedure, facts, item)
        for item in record["required_documentation"]
    ]


def _evaluate_checklist_item(
    procedure: ProcedureObject, facts: Optional[ClinicalFactsBundle], item: dict
) -> ChecklistItemResult:
    item_id = item["item_id"]
    label = item["label"]

    if item_id == "tooth_number":
        if procedure.tooth_number_fdi is not None:
            return _checklist_found(item_id, label, _first_source_quote(procedure))
        return _checklist_missing(item_id, label)

    if item_id in ("surface_name", "surface_names"):
        evidence = _surface_name_evidence(procedure, minimum_count=2 if item_id == "surface_names" else 1)
        if evidence:
            return _checklist_found(item_id, label, evidence)
        return _checklist_missing(item_id, label)

    if item_id == "canal_count":
        if procedure.canal_count in (CanalCount.ONE_CANAL, CanalCount.TWO_CANAL, CanalCount.THREE_CANAL):
            return _checklist_found(item_id, label, _first_source_quote(procedure))
        if procedure.canal_count == CanalCount.UNCLEAR:
            return ChecklistItemResult(
                item_id=item_id,
                label=label,
                status=ChecklistItemStatus.REVIEW,
                evidence_quote=_first_source_quote(procedure),
            )
        return _checklist_missing(item_id, label)

    if item_id == "status":
        if procedure.status in (ProcedureStatus.PERFORMED, ProcedureStatus.PLANNED):
            return _checklist_found(item_id, label, _first_source_quote(procedure))
        if procedure.status in (ProcedureStatus.DISCUSSED, ProcedureStatus.UNCLEAR):
            return ChecklistItemResult(
                item_id=item_id,
                label=label,
                status=ChecklistItemStatus.REVIEW,
                evidence_quote=_first_source_quote(procedure),
            )
        return _checklist_missing(item_id, label)

    if item_id == "material":
        evidence = _quote_containing(procedure.source_quotes, ("kompozit", "geçici", "gecici"))
        if evidence:
            return _checklist_found(item_id, label, evidence)
        return _checklist_missing(item_id, label)

    if item_id in ("indication", "endo_diagnosis"):
        evidence = _fact_evidence(
            facts,
            categories=(FactCategory.CLINICAL_FINDINGS, FactCategory.ASSESSMENT),
            tooth_number_fdi=procedure.tooth_number_fdi,
        )
        if evidence:
            return _checklist_found(item_id, label, evidence)
        return _checklist_missing(item_id, label)

    if item_id == "radiograph":
        evidence = _fact_evidence(
            facts,
            categories=(FactCategory.CLINICAL_FINDINGS,),
            text_needles=("röntgen", "rontgen", "periapikal", "radyograf"),
            tooth_number_fdi=procedure.tooth_number_fdi,
        )
        if evidence:
            return _checklist_found(item_id, label, evidence)
        return _checklist_missing(item_id, label)

    return _checklist_missing(item_id, label)


def _determine_match_state(candidate_count: int, checklist: list[ChecklistItemResult]) -> CodeMatchState:
    if candidate_count == 0:
        return CodeMatchState.NO_MATCH
    if candidate_count > 1:
        return CodeMatchState.AMBIGUOUS_MULTIPLE_CANDIDATES
    if any(item.status == ChecklistItemStatus.MISSING for item in checklist):
        return CodeMatchState.INSUFFICIENT_DOCUMENTATION
    if any(item.status == ChecklistItemStatus.REVIEW for item in checklist):
        return CodeMatchState.NEEDS_REVIEW
    return CodeMatchState.CONFIRMED_BY_DOCUMENTATION


def _ambiguity_note(procedure: ProcedureObject, candidates: list[dict]) -> Optional[str]:
    if not candidates:
        return "Kapalı fixture code DB içinde eşleşen aday yok; hekim manuel değerlendirmeli."
    if len(candidates) <= 1:
        return None
    if procedure.surface_count == SurfaceCount.UNCLEAR:
        return "Yüzey sayısı net değil; birden çok kompozit dolgu adayı hekim seçimi gerektirir."
    if procedure.canal_count == CanalCount.UNCLEAR:
        return "Kanal sayısı net değil; birden çok kanal tedavisi adayı hekim seçimi gerektirir."
    return "Birden çok aday bulundu; hekim seçim yapmalı."


def _checklist_found(item_id: str, label: str, evidence_quote: str) -> ChecklistItemResult:
    return ChecklistItemResult(
        item_id=item_id,
        label=label,
        status=ChecklistItemStatus.FOUND,
        evidence_quote=evidence_quote,
    )


def _checklist_missing(item_id: str, label: str) -> ChecklistItemResult:
    return ChecklistItemResult(item_id=item_id, label=label, status=ChecklistItemStatus.MISSING)


def _first_source_quote(procedure: ProcedureObject) -> str:
    return procedure.source_quotes[0] if procedure.source_quotes else ""


def _surface_name_evidence(procedure: ProcedureObject, minimum_count: int) -> Optional[str]:
    surface_terms = (
        "mesial",
        "distal",
        "okluzal",
        "bukkal",
        "lingual",
        "palatinal",
        "servikal",
        "insizal",
    )
    for quote in procedure.source_quotes:
        normalized = _normalize_lookup_text(quote)
        if sum(1 for term in surface_terms if term in normalized) >= minimum_count:
            return quote
    return None


def _quote_containing(quotes: list[str], needles: tuple[str, ...]) -> Optional[str]:
    for quote in quotes:
        if _has_any(_normalize_lookup_text(quote), needles):
            return quote
    return None


def _fact_evidence(
    facts: Optional[ClinicalFactsBundle],
    categories: tuple[FactCategory, ...],
    tooth_number_fdi: Optional[int],
    text_needles: tuple[str, ...] = (),
) -> Optional[str]:
    if facts is None:
        return None
    for fact in facts.facts:
        if fact.category not in categories or fact.source_role != DentistRole.DENTIST:
            continue
        if tooth_number_fdi is not None and fact.tooth_number_fdi not in (None, tooth_number_fdi):
            continue
        haystack = _normalize_lookup_text(f"{fact.text} {fact.source_quote}")
        if text_needles and not _has_any(haystack, text_needles):
            continue
        return fact.source_quote
    return None


def _loads_llm_json_object(raw_output: str) -> object:
    stripped = raw_output.strip()
    data, end_idx = json.JSONDecoder().raw_decode(stripped)
    trailing = stripped[end_idx:].strip()
    compact_trailing = "".join(ch for ch in trailing if not ch.isspace())
    if compact_trailing and any(ch not in "}`" for ch in compact_trailing):
        raise ValueError("JSON nesnesinden sonra anlamlı metin var")
    return data


def _first_present(data: dict, keys: tuple[str, ...], default: object = ...):
    for key in keys:
        if key in data:
            return data[key]
    if default is ...:
        raise KeyError(keys[0])
    return default


def _normalize_lookup_text(text: str) -> str:
    return text.casefold().replace("i̇", "i")


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)
