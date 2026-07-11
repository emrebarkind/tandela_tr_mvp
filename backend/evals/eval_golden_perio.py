"""Real-Gemini isolated eval for single- and multi-tooth perio prompts.

Run locally with synthetic golden-set dictations only:
    cd backend && python3 -m evals.eval_golden_perio
"""

from __future__ import annotations

import json
import traceback
from typing import Optional

from google.genai import types
from pydantic import BaseModel, Field

from app.pipeline.types import PerioMeasurement, PerioSite
from app.prompts.loader import load_system_prompt
from app.providers.gemini_provider import GeminiLLMProvider, _strip_json_fences


SINGLE_PROMPT = "perio_extraction.md"
MULTI_PROMPT = "perio_multi_tooth_extraction.md"

MULTI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "tooth_segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tooth_number_fdi": {"type": "integer"},
                    "source_quote": {"type": "string"},
                    "is_uncertain": {"type": "boolean"},
                    "sites": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "site": {
                                    "type": "string",
                                    "enum": ["MB", "B", "DB", "ML", "L", "DL"],
                                },
                                "pocket_depth_mm": {"type": "integer"},
                                "gingival_margin_mm": {"type": "integer"},
                                "bleeding_on_probing": {"type": "boolean"},
                                "plaque": {"type": "boolean"},
                                "recession_mm": {"type": "integer"},
                                "is_uncertain": {"type": "boolean"},
                            },
                            "required": ["site"],
                        },
                    },
                },
                "required": [
                    "tooth_number_fdi",
                    "source_quote",
                    "is_uncertain",
                    "sites",
                ],
            },
        },
        "unassigned_segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_quote": {"type": "string"},
                    "is_uncertain": {"type": "boolean"},
                },
                "required": ["source_quote", "is_uncertain"],
            },
        },
        "uncertain_items": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["tooth_segments", "unassigned_segments", "uncertain_items"],
}


class PerioEvalGeminiProvider(GeminiLLMProvider):
    """Real Gemini provider with enough output budget for multi-tooth JSON."""

    def complete(self, system_prompt: str, user_input: str) -> str:
        response_schema = MULTI_RESPONSE_SCHEMA if "tooth_segments" in system_prompt else None
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.0,
            response_mime_type="application/json",
            max_output_tokens=8192,
            response_json_schema=response_schema,
        )
        response = self._client.models.generate_content(
            model=self.model,
            contents=user_input,
            config=config,
        )
        return _strip_json_fences(response.text or "")


class UnassignedPerioSegment(BaseModel):
    source_quote: str
    is_uncertain: bool


class PerioExtractionResult(BaseModel):
    measurements: list[PerioMeasurement] = Field(default_factory=list)
    unassigned_segments: list[UnassignedPerioSegment] = Field(default_factory=list)
    uncertain_items: list[str] = Field(default_factory=list)


class PerioSiteValues(BaseModel):
    site: PerioSite
    pocket_depth_mm: Optional[int] = None
    gingival_margin_mm: Optional[int] = None
    bleeding_on_probing: Optional[bool] = None
    plaque: Optional[bool] = None
    recession_mm: Optional[int] = None
    is_uncertain: bool = False


class ToothPerioSegment(BaseModel):
    tooth_number_fdi: int
    source_quote: str
    is_uncertain: bool = False
    sites: list[PerioSiteValues] = Field(default_factory=list)


class MultiToothRawResult(BaseModel):
    tooth_segments: list[ToothPerioSegment] = Field(default_factory=list)
    unassigned_segments: list[UnassignedPerioSegment] = Field(default_factory=list)
    uncertain_items: list[str] = Field(default_factory=list)


SCENARIOS = (
    {
        "name": "Perio A",
        "dictation": "16 bukkal üç dört dört, kanama yok, plak var.",
        "prompt_file": SINGLE_PROMPT,
        "input_label": "Single-tooth dentist periodontal dictation",
    },
    {
        "name": "Perio B",
        "dictation": "16'da birkaç yerde dört beş civarı var, tam emin değilim.",
        "prompt_file": SINGLE_PROMPT,
        "input_label": "Single-tooth dentist periodontal dictation",
    },
    {
        "name": "Perio C",
        "dictation": (
            "16 bukkal üç dört dört, kanama yok, plak var. "
            "17'ye geçiyorum, bukkal iki üç iki, kanama var, plak yok."
        ),
        "prompt_file": MULTI_PROMPT,
        "input_label": "Multi-tooth dentist periodontal dictation",
    },
    {
        "name": "Perio D",
        "dictation": "Üç dört dört, kanama yok. Sonra iki üç iki, kanama var.",
        "prompt_file": MULTI_PROMPT,
        "input_label": "Multi-tooth dentist periodontal dictation",
    },
    {
        "name": "Perio E",
        "dictation": "16 bukkal üç dört dört, kanama yok. Sonra iki üç iki, kanama var.",
        "prompt_file": MULTI_PROMPT,
        "input_label": "Multi-tooth dentist periodontal dictation",
    },
)


def _build_user_input(label: str, dictation: str) -> str:
    return f"{label}:\n{dictation}"


def _normalize_multi_result(raw_data: dict) -> PerioExtractionResult:
    """Deterministically expand compact tooth segments to six site records."""
    raw_result = MultiToothRawResult.model_validate(raw_data)
    measurements: list[PerioMeasurement] = []
    for segment in raw_result.tooth_segments:
        values_by_site = {values.site: values for values in segment.sites}
        assert len(values_by_site) == len(segment.sites), "duplicate perio site in segment"
        for site in PerioSite:
            values = values_by_site.get(site)
            measurements.append(
                PerioMeasurement(
                    tooth_number_fdi=segment.tooth_number_fdi,
                    site=site,
                    pocket_depth_mm=values.pocket_depth_mm if values else None,
                    gingival_margin_mm=values.gingival_margin_mm if values else None,
                    bleeding_on_probing=values.bleeding_on_probing if values else None,
                    plaque=values.plaque if values else None,
                    recession_mm=values.recession_mm if values else None,
                    source_quote=segment.source_quote,
                    is_uncertain=segment.is_uncertain or bool(values and values.is_uncertain),
                )
            )
    return PerioExtractionResult(
        measurements=measurements,
        unassigned_segments=raw_result.unassigned_segments,
        uncertain_items=raw_result.uncertain_items,
    )


def _measurements_for_tooth(
    result: PerioExtractionResult,
    tooth: int,
) -> dict[PerioSite, PerioMeasurement]:
    items = [item for item in result.measurements if item.tooth_number_fdi == tooth]
    assert len(items) == 6, f"tooth {tooth}: exactly six site records expected"
    assert {item.site for item in items} == set(PerioSite)
    return {item.site: item for item in items}


def _assert_forbidden_raw_fields(raw_data: dict) -> None:
    serialized = json.dumps(raw_data, ensure_ascii=False)
    for field in (
        "attachment_level_mm",
        "mobility_grade",
        "furcation_grade",
        "furcation_site",
    ):
        assert field not in serialized


def _assert_a(result: PerioExtractionResult, raw_data: dict) -> None:
    by_site = _measurements_for_tooth(result, 16)
    for site, depth in zip((PerioSite.MB, PerioSite.B, PerioSite.DB), (3, 4, 4)):
        item = by_site[site]
        assert item.pocket_depth_mm == depth
        assert item.bleeding_on_probing is False
        assert item.plaque is True
        assert item.is_uncertain is False
    assert all(item.source_quote == SCENARIOS[0]["dictation"] for item in by_site.values())
    assert result.uncertain_items == []
    _assert_forbidden_raw_fields(raw_data)


def _assert_b(result: PerioExtractionResult, raw_data: dict) -> None:
    by_site = _measurements_for_tooth(result, 16)
    for item in by_site.values():
        assert item.pocket_depth_mm is None
        assert item.gingival_margin_mm is None
        assert item.recession_mm is None
        assert item.bleeding_on_probing is None
        assert item.plaque is None
        assert item.is_uncertain is True
        assert item.source_quote == SCENARIOS[1]["dictation"]
    text = " ".join(result.uncertain_items).casefold()
    assert "16" in text and ("net değil" in text or "belirsiz" in text)
    _assert_forbidden_raw_fields(raw_data)


def _assert_c(result: PerioExtractionResult, raw_data: dict) -> None:
    assert len(result.measurements) == 12
    assert result.unassigned_segments == []
    assert result.uncertain_items == []
    expected = {
        16: ("16 bukkal üç dört dört, kanama yok, plak var.", (3, 4, 4), False, True),
        17: ("17'ye geçiyorum, bukkal iki üç iki, kanama var, plak yok.", (2, 3, 2), True, False),
    }
    for tooth, (quote, depths, bleeding, plaque) in expected.items():
        by_site = _measurements_for_tooth(result, tooth)
        for site, depth in zip((PerioSite.MB, PerioSite.B, PerioSite.DB), depths):
            item = by_site[site]
            assert item.pocket_depth_mm == depth
            assert item.bleeding_on_probing is bleeding
            assert item.plaque is plaque
            assert item.is_uncertain is False
        assert all(item.source_quote == quote for item in by_site.values())
    _assert_forbidden_raw_fields(raw_data)


def _assert_d(result: PerioExtractionResult, raw_data: dict) -> None:
    assert result.measurements == [], "Perio D must not invent tooth measurements"
    expected_quotes = {
        "Üç dört dört, kanama yok.",
        "Sonra iki üç iki, kanama var.",
    }
    assert {item.source_quote for item in result.unassigned_segments} == expected_quotes
    assert all(item.is_uncertain is True for item in result.unassigned_segments)
    assert "tooth_number_fdi" not in json.dumps(
        raw_data.get("unassigned_segments", []), ensure_ascii=False
    )
    text = " ".join(result.uncertain_items).casefold()
    assert "diş" in text
    _assert_forbidden_raw_fields(raw_data)


def _assert_e(result: PerioExtractionResult, raw_data: dict) -> None:
    assert len(result.measurements) == 6
    by_site = _measurements_for_tooth(result, 16)
    for site, depth in zip((PerioSite.MB, PerioSite.B, PerioSite.DB), (3, 4, 4)):
        item = by_site[site]
        assert item.pocket_depth_mm == depth
        assert item.bleeding_on_probing is False
        assert item.is_uncertain is False
    assert all(
        item.source_quote == "16 bukkal üç dört dört, kanama yok."
        for item in by_site.values()
    )
    assert len(result.unassigned_segments) == 1
    assert result.unassigned_segments[0].source_quote == "Sonra iki üç iki, kanama var."
    assert result.unassigned_segments[0].is_uncertain is True
    assert all(item.tooth_number_fdi == 16 for item in result.measurements)
    text = " ".join(result.uncertain_items).casefold()
    assert "diş" in text
    _assert_forbidden_raw_fields(raw_data)


ASSERTIONS = {
    "Perio A": _assert_a,
    "Perio B": _assert_b,
    "Perio C": _assert_c,
    "Perio D": _assert_d,
    "Perio E": _assert_e,
}


def run_scenario(scenario: dict[str, str], llm: GeminiLLMProvider) -> bool:
    print("=" * 78)
    print(f"{scenario['name']} — gerçek Gemini ham çıktı (parse öncesi)")
    print(f"Model: {llm.model}")
    print(f"Girdi: {scenario['dictation']}")
    print("-" * 78)
    try:
        raw = llm.complete(
            load_system_prompt(scenario["prompt_file"]),
            _build_user_input(scenario["input_label"], scenario["dictation"]),
        )
        print(raw)
        print("-" * 78)
        raw_data = json.loads(raw)
        result = (
            _normalize_multi_result(raw_data)
            if scenario["prompt_file"] == MULTI_PROMPT
            else PerioExtractionResult.model_validate(raw_data)
        )
        print("Parse edilmiş PerioMeasurement sonucu:")
        print(result.model_dump_json(exclude_none=False, indent=2))
        ASSERTIONS[scenario["name"]](result, raw_data)
    except Exception as exc:  # noqa: BLE001 - visible manual eval diagnostics.
        print(f"SONUÇ: BAŞARISIZ — {type(exc).__name__}: {exc}")
        print(traceback.format_exc())
        return False
    print("SONUÇ: GEÇTİ")
    return True


def main() -> int:
    try:
        llm = PerioEvalGeminiProvider()
    except RuntimeError as exc:
        print(f"DURDU: {exc}")
        return 2
    outcomes = [run_scenario(scenario, llm) for scenario in SCENARIOS]
    passed = sum(outcomes)
    print("=" * 78)
    print(f"ÖZET: {passed}/{len(outcomes)} perio senaryosu geçti")
    return 0 if passed == len(outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
