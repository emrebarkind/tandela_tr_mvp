from __future__ import annotations

import json
import unittest

from app.pipeline import stages
from app.pipeline.stages import SourceRoleInvariantViolation
from app.pipeline.types import (
    CanalCount,
    ChecklistItemStatus,
    ClinicalFact,
    ClinicalFactsBundle,
    DentalCondition,
    Dentition,
    DentistRole,
    FactCategory,
    ProcedureStatus,
    RoleStatus,
    SpeakerLabelledTranscript,
    SurfaceCount,
    ToothGroup,
    ToothSurface,
    ToothType,
    Utterance,
    derive_fdi_classification,
)
from app.providers.gemini_audio_provider import normalize_gemini_audio_response
from app.providers.llm import LLMProvider


class ScriptedLLM(LLMProvider):
    def __init__(self, outputs: list[dict] | list[str]) -> None:
        self.outputs = list(outputs)

    def complete(self, system_prompt: str, user_input: str) -> str:
        if not self.outputs:
            raise AssertionError("ScriptedLLM output kalmadı")
        output = self.outputs.pop(0)
        if isinstance(output, str):
            return output
        return json.dumps(output, ensure_ascii=False)


class PipelineContractTests(unittest.TestCase):
    def test_assign_roles_floors_single_utterance_clear_to_review_needed(self) -> None:
        transcript = SpeakerLabelledTranscript(
            session_id="role-floor",
            utterances=[Utterance(speaker_id="A", text="Merhaba.", start_sec=0, end_sec=1)],
        )
        llm = ScriptedLLM(
            [
                {
                    "assignments": [
                        {
                            "speaker_id": "A",
                            "role": "dentist",
                            "status": "clear",
                            "utterance_count": 1,
                            "reason": "Model clear dedi.",
                        }
                    ],
                    "manual_review_required": False,
                }
            ]
        )

        result = stages.assign_roles(transcript, llm)

        self.assertTrue(result.manual_review_required)
        self.assertTrue(result.requires_role_review)
        self.assertEqual(result.assignments[0].status, RoleStatus.REVIEW_NEEDED)

    def test_note_generation_rejects_paraphrase_and_falls_back_to_fact_text(self) -> None:
        facts = ClinicalFactsBundle(
            session_id="note-fallback",
            facts=[
                ClinicalFact(
                    category=FactCategory.PATIENT_COMPLAINT,
                    text="Hasta soğuk hassasiyeti tarif etti.",
                    source_quote="soğukta artıyordu",
                    source_role=DentistRole.PATIENT,
                    source_speaker="B",
                )
            ],
            uncertain_items=["Diş numarası net değil."],
        )
        llm = ScriptedLLM(
            [
                {
                    "patient_complaint": [
                        {
                            "sentence_id": "bad",
                            "text": "Hasta soğuğa hassasiyet söyledi.",
                            "source_role": "patient",
                            "source_quote": "soğukta artıyordu",
                        }
                    ],
                    "history": [],
                    "clinical_findings": [],
                    "assessment": [],
                    "treatment_plan": [],
                    "procedures_note": [],
                    "uncertain_items": ["Diş numarası net değil."],
                    "is_draft": True,
                }
            ]
        )

        note = stages.generate_clinical_note(facts, llm)

        self.assertEqual(note.patient_complaint[0].text, "Hasta soğuk hassasiyeti tarif etti.")
        self.assertEqual(note.patient_complaint[0].source_quote, "soğukta artıyordu")
        self.assertTrue(note.is_draft)

    def test_patient_procedure_claim_does_not_become_procedure_object(self) -> None:
        facts = ClinicalFactsBundle(
            session_id="patient-procedure",
            facts=[
                ClinicalFact(
                    category=FactCategory.PROCEDURES,
                    text="Geçen sene kanal tedavisi yapılmıştı.",
                    source_quote="geçen sene bu dişe kanal tedavisi yapılmıştı",
                    source_role=DentistRole.PATIENT,
                    source_speaker="B",
                    status=ProcedureStatus.PERFORMED,
                )
            ],
        )

        procedures = stages.extract_procedures(facts)

        self.assertEqual(procedures, [])

    def test_unknown_source_role_still_trips_invariant(self) -> None:
        facts = ClinicalFactsBundle(
            session_id="unknown-source",
            facts=[
                ClinicalFact(
                    category=FactCategory.CLINICAL_FINDINGS,
                    text="Kaynak rol bilinmiyor.",
                    source_quote="kaynak rol bilinmiyor",
                    source_role=DentistRole.UNKNOWN,
                    source_speaker="X",
                )
            ],
        )

        with self.assertRaises(SourceRoleInvariantViolation):
            stages.extract_procedures(facts)

    def test_composite_matching_keeps_missing_fdi_and_surface_names(self) -> None:
        facts = ClinicalFactsBundle(
            session_id="composite-missing-docs",
            facts=[
                ClinicalFact(
                    category=FactCategory.CLINICAL_FINDINGS,
                    text="Üst sağ bölgede çürük var.",
                    source_quote="üst sağ bölgede çürük var",
                    source_role=DentistRole.DENTIST,
                    source_speaker="A",
                    is_uncertain=True,
                ),
                ClinicalFact(
                    category=FactCategory.PROCEDURES,
                    text="İki yüzlü kompozit dolgu yaptık bugün.",
                    source_quote="İki yüzlü kompozit dolgu yaptık bugün",
                    source_role=DentistRole.DENTIST,
                    source_speaker="A",
                    status=ProcedureStatus.PERFORMED,
                ),
            ],
        )

        procedures = stages.extract_procedures(facts)
        bundles = stages.match_codes_and_checklist(procedures, facts)
        result = bundles[0].match_results[0]
        checklist = {item.item_id: item.status for item in result.checklist}

        self.assertEqual(procedures[0].procedure_family, "kompozit_dolgu")
        self.assertIsNone(procedures[0].tooth_number_fdi)
        self.assertEqual(procedures[0].surface_count, SurfaceCount.TWO_SURFACE)
        self.assertEqual(checklist["tooth_number"], ChecklistItemStatus.MISSING)
        self.assertEqual(checklist["surface_names"], ChecklistItemStatus.MISSING)
        self.assertEqual(checklist["indication"], ChecklistItemStatus.FOUND)

    def test_fdi_classification_accepts_permanent_and_primary_ranges(self) -> None:
        cases = {
            11: (Dentition.PERMANENT, ToothType.ANTERIOR, ToothGroup.ANTERIOR),
            45: (Dentition.PERMANENT, ToothType.PREMOLAR, ToothGroup.POSTERIOR),
            47: (Dentition.PERMANENT, ToothType.MOLAR, ToothGroup.POSTERIOR),
            52: (Dentition.PRIMARY, ToothType.ANTERIOR, ToothGroup.ANTERIOR),
            84: (Dentition.PRIMARY, ToothType.MOLAR, ToothGroup.POSTERIOR),
            19: (None, None, None),
            50: (None, None, None),
        }

        for tooth_number, expected in cases.items():
            with self.subTest(tooth_number=tooth_number):
                self.assertEqual(derive_fdi_classification(tooth_number), expected)
                self.assertEqual(stages._is_valid_fdi(tooth_number), expected[0] is not None)

    def test_endodontic_matching_uses_fdi_tooth_type_not_canal_count(self) -> None:
        facts = ClinicalFactsBundle(
            session_id="endo-ambiguous",
            facts=[
                ClinicalFact(
                    category=FactCategory.CLINICAL_FINDINGS,
                    text="46 numarada derin çürük görüyorum.",
                    source_quote="46 numarada derin çürük görüyorum",
                    source_role=DentistRole.DENTIST,
                    source_speaker="A",
                    tooth_number_fdi=46,
                ),
                ClinicalFact(
                    category=FactCategory.PROCEDURES,
                    text="46 numara için kanal tedavisi planlandı.",
                    source_quote="46 numara için kanal tedavisi planlandı",
                    source_role=DentistRole.DENTIST,
                    source_speaker="A",
                    tooth_number_fdi=46,
                    status=ProcedureStatus.PLANNED,
                ),
            ],
        )

        procedures = stages.extract_procedures(facts)
        bundles = stages.match_codes_and_checklist(procedures, facts)
        checklist = {item.item_id: item.status for item in bundles[0].match_results[0].checklist}

        self.assertEqual(procedures[0].canal_count, CanalCount.UNCLEAR)
        self.assertEqual(procedures[0].dentition, Dentition.PERMANENT)
        self.assertEqual(procedures[0].tooth_type, ToothType.MOLAR)
        self.assertEqual(procedures[0].tooth_group, ToothGroup.POSTERIOR)
        self.assertEqual([candidate.code for candidate in bundles[0].candidates], ["END330"])
        self.assertEqual(checklist["kanal_sayisi_belirtildi_mi"], ChecklistItemStatus.REVIEW)
        self.assertTrue(bundles[0].dentist_must_choose)

    def test_dental_chart_extraction_adds_surface_and_condition_without_guessing(self) -> None:
        facts = ClinicalFactsBundle(
            session_id="chart-enrichment",
            facts=[
                ClinicalFact(
                    category=FactCategory.PROCEDURES,
                    text="46 numarada MOD kompozit dolgu planlandı.",
                    source_quote="46 numarada MOD kompozit dolgu planlandı",
                    source_role=DentistRole.DENTIST,
                    source_speaker="A",
                    tooth_number_fdi=46,
                    status=ProcedureStatus.PLANNED,
                )
            ],
        )
        llm = ScriptedLLM(
            [
                [
                    {
                        "tooth_fdi": 46,
                        "surfaces": ["M", "O", "D"],
                        "condition": "composite",
                        "status": "planned",
                        "source_quote": "46 numarada MOD kompozit dolgu planlandı",
                    }
                ]
            ]
        )

        procedures = stages.extract_dental_chart_commands(facts, llm)

        self.assertEqual(procedures[0].tooth_number_fdi, 46)
        self.assertEqual(procedures[0].surfaces, [ToothSurface.MESIAL, ToothSurface.OCCLUSAL, ToothSurface.DISTAL])
        self.assertEqual(procedures[0].condition, DentalCondition.COMPOSITE)

    def test_code_explanation_llm_cannot_invent_candidate_code(self) -> None:
        facts = ClinicalFactsBundle(
            session_id="invented-code",
            facts=[
                ClinicalFact(
                    category=FactCategory.PROCEDURES,
                    text="46 numara için kanal tedavisi planlandı.",
                    source_quote="46 numara için kanal tedavisi planlandı",
                    source_role=DentistRole.DENTIST,
                    source_speaker="A",
                    tooth_number_fdi=46,
                    status=ProcedureStatus.PLANNED,
                )
            ],
        )
        llm = ScriptedLLM(
            [
                {
                    "explanations": [
                        {"code": "UYDURMA-KOD", "fit_reason": "Yanlış aday.", "caveat": None}
                    ],
                    "ambiguity_note": None,
                    "dentist_must_choose": True,
                }
            ]
        )

        procedures = stages.extract_procedures(facts)
        bundles = stages.match_codes_and_checklist(procedures, facts, llm)

        self.assertEqual([candidate.code for candidate in bundles[0].candidates], ["END330"])
        self.assertEqual(bundles[0].explanations, [])

    def test_gemini_audio_normalizes_role_like_speaker_labels(self) -> None:
        transcript = normalize_gemini_audio_response(
            "audio-speakers",
            {
                "utterances": [
                    {"speaker_id": "Doktor", "text": "46 numarada derin çürük görüyorum."},
                    {"speaker_id": "Hasta", "text": "Sağ alt tarafta ağrım var."},
                    {"speaker_id": "Asistan", "text": "Röntgeni açıyorum."},
                ]
            },
        )

        self.assertEqual([utterance.speaker_id for utterance in transcript.utterances], ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main()
