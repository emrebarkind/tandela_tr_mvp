"""Real-Gemini isolated eval for tooth-level mobility and furcation extraction.

Run locally with synthetic golden-set dictations only:
    cd backend && python3 -m evals.eval_golden_perio_summary
"""

from __future__ import annotations

import json
from typing import Optional

from google.genai import types
from pydantic import BaseModel, Field

from app.pipeline.types import ToothPerioSummary
from app.prompts.loader import load_system_prompt
from app.providers.gemini_provider import GeminiLLMProvider, _strip_json_fences


PROMPT_FILE = "perio_tooth_summary_extraction.md"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summaries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tooth_number_fdi": {"type": "integer"},
                    "mobility_grade": {"type": ["integer", "null"]},
                    "furcation_grade": {"type": ["integer", "null"]},
                    "furcation_site": {
                        "type": ["string", "null"],
                        "enum": ["buccal", "lingual", "palatal", "mesial", "distal", None],
                    },
                    "source_quote": {"type": "string"},
                    "is_uncertain": {"type": "boolean"},
                },
                "required": [
                    "tooth_number_fdi",
                    "mobility_grade",
                    "furcation_grade",
                    "furcation_site",
                    "source_quote",
                    "is_uncertain",
                ],
            },
        },
        "uncertain_items": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summaries", "uncertain_items"],
}


class PerioSummaryEvalProvider(GeminiLLMProvider):
    def complete(self, system_prompt: str, user_input: str) -> str:
        response = self._client.models.generate_content(
            model=self.model,
            contents=user_input,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.0,
                response_mime_type="application/json",
                response_json_schema=RESPONSE_SCHEMA,
                max_output_tokens=4096,
            ),
        )
        return _strip_json_fences(response.text or "")


class ExtractedToothSummary(BaseModel):
    tooth_number_fdi: int
    mobility_grade: Optional[int] = None
    furcation_grade: Optional[int] = None
    furcation_site: Optional[str] = None
    source_quote: str
    is_uncertain: bool = False

    def clinical_summary(self) -> ToothPerioSummary:
        return ToothPerioSummary.model_validate(
            self.model_dump(include={
                "tooth_number_fdi",
                "mobility_grade",
                "furcation_grade",
                "furcation_site",
            })
        )


class ExtractionResult(BaseModel):
    summaries: list[ExtractedToothSummary] = Field(default_factory=list)
    uncertain_items: list[str] = Field(default_factory=list)


SCENARIOS = (
    ("Perio Diş Özeti F", "16 mobilite bir, furkasyon iki bukkal."),
    ("Perio Diş Özeti G", "16 biraz oynuyor gibi."),
    ("Perio Diş Özeti H", "11 furkasyon bir."),
)


def _contains(items: list[str], *terms: str) -> bool:
    text = " ".join(items).casefold()
    return all(term.casefold() in text for term in terms)


def _assert_result(index: int, result: ExtractionResult) -> None:
    assert len(result.summaries) == 1
    extracted = result.summaries[0]
    clinical = extracted.clinical_summary()
    expected_quote = SCENARIOS[index][1]
    assert extracted.source_quote == expected_quote

    if index == 0:
        assert clinical.tooth_number_fdi == 16
        assert clinical.mobility_grade == 1
        assert clinical.furcation_grade == 2
        assert clinical.furcation_site == "buccal"
        assert extracted.is_uncertain is False
        assert result.uncertain_items == []
    elif index == 1:
        assert clinical.tooth_number_fdi == 16
        assert extracted.mobility_grade is None
        assert extracted.is_uncertain is True
        assert _contains(result.uncertain_items, "mobilite", "net") or _contains(
            result.uncertain_items, "mobilite", "belirsiz"
        )
    else:
        assert clinical.tooth_number_fdi == 11
        # Assert the raw parsed model rejected it, not merely the domain model's
        # defensive validator clearing it afterward.
        assert extracted.furcation_grade is None
        assert extracted.furcation_site is None
        assert clinical.furcation_grade is None
        assert clinical.furcation_site is None
        assert extracted.is_uncertain is True
        assert _contains(result.uncertain_items, "furkasyon", "geçerli değil")


def main() -> None:
    provider = PerioSummaryEvalProvider()
    prompt = load_system_prompt(PROMPT_FILE)
    passed = 0

    print(f"Model: {provider.model}")
    for index, (name, dictation) in enumerate(SCENARIOS):
        raw = provider.complete(prompt, f"Dentist dictation:\n{dictation}")
        print(f"\n=== {name} HAM JSON ===")
        print(raw)
        parsed = ExtractionResult.model_validate(json.loads(raw))
        print(f"=== {name} PARSE EDİLMİŞ ===")
        print(parsed.model_dump_json(indent=2))
        _assert_result(index, parsed)
        passed += 1
        print(f"{name}: GEÇTİ")

    print(f"\nSONUÇ: {passed}/{len(SCENARIOS)} senaryo geçti")


if __name__ == "__main__":
    main()
