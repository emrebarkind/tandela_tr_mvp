from __future__ import annotations

import json
import unittest
from unittest.mock import patch

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
    RoleLabelledTranscript,
    RoleLabelledUtterance,
    SpeakerLabelledTranscript,
    SurfaceCount,
    ToothGroup,
    ToothSurface,
    ToothType,
    ToothPerioSummary,
    PerioSite,
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
    def test_patient_identity_and_medical_history_preserve_sources_without_deriving_birth_date(self) -> None:
        transcript = RoleLabelledTranscript(
            session_id="identity-history",
            utterances=[
                RoleLabelledUtterance(speaker_id="A", role=DentistRole.DENTIST, text="Tıbbi geçmişiniz ve alerjiniz var mı?", start_sec=0, end_sec=1),
                RoleLabelledUtterance(speaker_id="B", role=DentistRole.PATIENT, text="Adım Ayşe Yılmaz, otuz beş yaşındayım, öğretmenim. Düzenli tansiyon ilacı kullanıyorum, alerjim yok.", start_sec=1, end_sec=5),
            ],
        )
        facts_llm = ScriptedLLM([{
            "patient_information": {
                "display_name": {"value": "Ayşe Yılmaz", "source_quote": "Adım Ayşe Yılmaz", "source_role": "patient", "source_speaker": "B", "is_uncertain": False},
                "age": {"value": "35", "source_quote": "otuz beş yaşındayım", "source_role": "patient", "source_speaker": "B", "is_uncertain": False},
                "date_of_birth": {"value": "1991-01-01", "source_quote": "otuz beş yaşındayım", "source_role": "patient", "source_speaker": "B", "is_uncertain": False},
                "occupation": {"value": "öğretmen", "source_quote": "öğretmenim", "source_role": "patient", "source_speaker": "B", "is_uncertain": False},
            },
            "medical_history": {
                "regular_medication": {"value": True, "detail": "tansiyon ilacı", "source_quote": "Düzenli tansiyon ilacı kullanıyorum", "source_role": "patient", "source_speaker": "B", "is_uncertain": False},
                "drug_allergy": {"value": False, "detail": None, "source_quote": "alerjim yok", "source_role": "patient", "source_speaker": "B", "is_uncertain": False},
            },
            "facts": [],
            "uncertain_items": [],
        }])

        facts = stages.extract_clinical_facts(transcript, facts_llm)

        self.assertEqual(facts.patient_information.display_name.value, "Ayşe Yılmaz")
        self.assertEqual(facts.patient_information.age.value, "35")
        self.assertEqual(facts.patient_information.occupation.value, "öğretmen")
        self.assertIsNone(facts.patient_information.date_of_birth)
        self.assertTrue(any("doğum tarihine çevrilmedi" in item for item in facts.uncertain_items))
        self.assertIs(facts.medical_history.regular_medication.value, True)
        self.assertEqual(facts.medical_history.regular_medication.detail, "tansiyon ilacı")
        self.assertIs(facts.medical_history.drug_allergy.value, False)

        note = stages.generate_clinical_note(facts, ScriptedLLM([{
            "patient_complaint": [], "history": [], "clinical_findings": [], "assessment": [],
            "treatment_plan": [], "procedures_note": [], "uncertain_items": facts.uncertain_items, "is_draft": True,
        }]))
        self.assertEqual(note.patient_information, facts.patient_information)
        self.assertEqual(note.medical_history, facts.medical_history)

    def test_perio_site_mapping_preserves_mb_db_booleans_and_site_recession(self) -> None:
        llm = ScriptedLLM(
            [
                {
                    "tooth_segments": [
                        {
                            "tooth_number_fdi": 16,
                            "source_quote": "16 bukkal dört dört üç, kanama var, plak var.",
                            "is_uncertain": False,
                            "sites": [
                                {"site": "MB", "pocket_depth_mm": 4, "bleeding_on_probing": True, "plaque": True},
                                {"site": "B", "pocket_depth_mm": 4, "bleeding_on_probing": True, "plaque": True},
                                {"site": "DB", "pocket_depth_mm": 3, "bleeding_on_probing": True, "plaque": True},
                            ],
                        },
                        {
                            "tooth_number_fdi": 26,
                            "source_quote": "26 bukkal üç üç dört, recession bir milimetre bukkalde.",
                            "is_uncertain": False,
                            "sites": [
                                {"site": "MB", "pocket_depth_mm": 3},
                                {
                                    "site": "B",
                                    "pocket_depth_mm": 3,
                                    "gingival_margin_mm": 9,
                                    "recession_mm": 1,
                                },
                                {"site": "DB", "pocket_depth_mm": 4},
                            ],
                        },
                    ],
                    "unassigned_segments": [],
                    "uncertain_items": [],
                }
            ]
        )

        measurements, uncertain_items = stages.extract_perio_site_measurements(
            "sentetik perio diktesi", llm
        )
        by_tooth_site = {
            (item.tooth_number_fdi, item.site): item for item in measurements
        }

        self.assertEqual(by_tooth_site[(16, PerioSite.MB)].pocket_depth_mm, 4)
        self.assertEqual(by_tooth_site[(16, PerioSite.B)].pocket_depth_mm, 4)
        self.assertEqual(by_tooth_site[(16, PerioSite.DB)].pocket_depth_mm, 3)
        for site in (PerioSite.MB, PerioSite.B, PerioSite.DB):
            self.assertIs(by_tooth_site[(16, site)].bleeding_on_probing, True)
            self.assertIs(by_tooth_site[(16, site)].plaque, True)

        self.assertEqual(by_tooth_site[(26, PerioSite.MB)].pocket_depth_mm, 3)
        self.assertEqual(by_tooth_site[(26, PerioSite.B)].pocket_depth_mm, 3)
        self.assertEqual(by_tooth_site[(26, PerioSite.DB)].pocket_depth_mm, 4)
        self.assertIsNone(by_tooth_site[(26, PerioSite.MB)].recession_mm)
        self.assertEqual(by_tooth_site[(26, PerioSite.B)].recession_mm, 1)
        self.assertEqual(by_tooth_site[(26, PerioSite.B)].gingival_margin_mm, -1)
        self.assertEqual(by_tooth_site[(26, PerioSite.B)].attachment_level_mm, 4)
        self.assertIsNone(by_tooth_site[(26, PerioSite.DB)].recession_mm)
        self.assertEqual(uncertain_items, [])

    def test_perio_summary_invariant_clears_and_logs_ineligible_furcation(self) -> None:
        violating_summary = ToothPerioSummary.model_construct(
            tooth_number_fdi=11,
            mobility_grade=None,
            furcation_grade=2,
            furcation_site="buccal",
        )

        with patch.object(stages.logger, "warning") as warning:
            corrected = stages._enforce_perio_summary_invariant(violating_summary)

        self.assertIsNone(corrected.furcation_grade)
        self.assertIsNone(corrected.furcation_site)
        warning.assert_called_once_with(
            "perio_summary_invariant_corrected: tooth_number_fdi=%s "
            "reason=furcation_not_valid_for_tooth_type",
            11,
        )

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
