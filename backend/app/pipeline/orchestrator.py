"""
Uçtan uca pipeline orchestration (CLAUDE.md §3).

Audio capture → preprocessing → ASR → diarization → alignment →
role_assignment → [REVIEW GATE] → clinical facts extraction →
clinical note generation → procedure extraction → TDB code matching +
checklist → hekim review/edit/approve → export/copy.

Bu görevde her aşamanın İÇERİK üretimi STUB'tır (bkz. stages.py) — gerçek
ASR/DB çağrısı yok. `stages.assign_roles` İSTİSNA: gerçek bir LLM çağrısı
yapar (`LLMProvider` arabirimi arkasında, vendor TBD — CLAUDE.md §6/§10,
prompt `prompts/role_assignment.md`). Orchestration MANTIĞININ kendisi,
özellikle REVIEW GATE, GERÇEKTİR:

  role_assignment çıktısında herhangi bir konuşmacı `unresolved`/`unknown`/
  `review_needed` İSE YA DA `manual_review_required=True` İSE pipeline DURUR;
  clinical note üretmeden `PipelineStatus.NEEDS_DENTIST_ROLE_REVIEW` döner.

`assign_roles` kendi içinde fail-safe'tir: LLM çıktısı parse edilemezse,
beklenen konuşmacı kümesiyle uyuşmazsa, ya da geçersiz bir enum değeri
içerirse, sahte/iyimser bir atama ÜRETMEZ — hepsini `unknown`/`unresolved` +
`manual_review_required=True` yapar (CLAUDE.md §4.1).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from app.pipeline import stages
from app.pipeline.stages import SourceRoleInvariantViolation
from app.pipeline.types import (
    AudioRef,
    DentistReviewDecision,
    PipelineResult,
    PipelineStatus,
    RoleAssignmentResult,
    SpeakerLabelledTranscript,
    PerioSessionResult,
)
from app.providers.audio_processing import AudioProcessingProvider
from app.providers.llm import LLMProvider

logger = logging.getLogger(__name__)


def run_perio_pipeline(dictation: str, llm_provider: LLMProvider) -> PerioSessionResult:
    """Run the dedicated dentist-only perio dictation pipeline.

    Product decision: perio is a separate, explicitly dentist-started session,
    so role assignment is intentionally not called. The clinical-conversation
    REVIEW GATE remains unchanged and continues to govern `run_pipeline`.
    """
    if not dictation.strip():
        raise ValueError("Perio diktesi boş olamaz.")

    measurements_result, summaries_result = asyncio.run(
        _run_perio_extractions_parallel(dictation.strip(), llm_provider)
    )
    measurements, site_uncertainties = measurements_result
    tooth_summaries, summary_uncertainties = summaries_result
    uncertain_items = list(dict.fromkeys(site_uncertainties + summary_uncertainties))
    return PerioSessionResult(
        measurements=measurements,
        tooth_summaries=tooth_summaries,
        uncertain_items=uncertain_items,
    )


async def _run_perio_extractions_parallel(dictation: str, llm_provider: LLMProvider):
    return await asyncio.gather(
        asyncio.to_thread(stages.extract_perio_site_measurements, dictation, llm_provider),
        asyncio.to_thread(stages.extract_perio_tooth_summaries, dictation, llm_provider),
    )


def run_pipeline(
    audio: AudioRef, provider: AudioProcessingProvider, llm_provider: LLMProvider
) -> PipelineResult:
    """Audio capture'dan REVIEW GATE'e (veya ondan sonrasına) kadar çalışır.

    REVIEW GATE'i geçemezse burada durur ve clinical note/kod önerisi
    üretmeden `PipelineResult` döner (`status=NEEDS_DENTIST_ROLE_REVIEW`).
    Hekim rol düzeltmesi yaptıktan sonra akış `resume_after_role_review`
    ile devam eder.
    """
    result = PipelineResult(session_id=audio.session_id, status=PipelineStatus.OK)

    preprocessed = stages.preprocess_audio(audio)
    result.preprocessed_audio = preprocessed

    speaker_labelled = stages.transcribe_and_diarize_and_align(preprocessed, provider)
    result.speaker_labelled_transcript = speaker_labelled

    role_assignment = _time_pipeline_stage(
        "assign_roles",
        result.session_id,
        lambda: stages.assign_roles(speaker_labelled, llm_provider),
    )
    result.role_assignment = role_assignment

    if _review_gate_blocks(role_assignment):
        result.status = PipelineStatus.NEEDS_DENTIST_ROLE_REVIEW
        result.stopped_at_stage = "role_assignment"
        return result

    return _continue_after_role_assignment(result, speaker_labelled, role_assignment, llm_provider)


def resume_after_role_review(
    result: PipelineResult,
    speaker_labelled: SpeakerLabelledTranscript,
    corrected_role_assignment: RoleAssignmentResult,
    llm_provider: LLMProvider,
) -> PipelineResult:
    """Hekim, REVIEW GATE'te durdurulan rol atamasını düzelttikten sonra
    pipeline'ı devam ettirir.

    Düzeltilmiş atama TEKRAR REVIEW GATE'ten geçer: hekim düzeltmesi sonrası
    hâlâ unresolved/unknown bırakılmışsa (örn. gerçekten ayırt edilemeyen bir
    konuşmacı varsa) pipeline yine durur — varsayım üretilmez (CLAUDE.md §4.1).
    """
    if _review_gate_blocks(corrected_role_assignment):
        result.status = PipelineStatus.NEEDS_DENTIST_ROLE_REVIEW
        result.role_assignment = corrected_role_assignment
        result.stopped_at_stage = "role_assignment"
        return result

    return _continue_after_role_assignment(result, speaker_labelled, corrected_role_assignment, llm_provider)


def apply_dentist_review(
    result: PipelineResult, decision: DentistReviewDecision
) -> PipelineResult:
    """Hekim clinical note + kod önerilerini onayladıktan/düzelttikten sonra
    export'a hazırlar.

    Durum geçişi (CLAUDE.md §4.10 — her şey taslaktır, onay/export her zaman
    lisanslı hekimde):
      - `decision.approved=True`  → `PipelineStatus.APPROVED`. Bu, onay
        ÖNCESİ durumdan (`AWAITING_DENTIST_REVIEW`) AYRI bir terminal
        durumdur — onaylanmış bir akış "hâlâ hekim onayı bekliyor" durumuyla
        karıştırılamaz. Export henüz bu görevin kapsamı dışı; `APPROVED`,
        export'un (gerçek dosya/DB yazımı eklendiğinde) başlayacağı durumdur.
      - `decision.approved=False` → durum DEĞİŞMEZ
        (`AWAITING_DENTIST_REVIEW`'da kalır); hekim henüz onaylamadı, export'a
        geçilmez.

    Gerçek export (dosya/DB yazımı) bu görevin kapsamı dışında; o adım
    eklendiğinde `PipelineStatus.EXPORTED`'a geçiş burada DEĞİL, export
    fonksiyonunun kendisinde yapılır (export'un fiilen gerçekleştiğini
    onaylayan ayrı bir adım — "approved" ile "exported" aynı an değildir).
    """
    result.review_decision = decision
    if decision.approved:
        result.status = PipelineStatus.APPROVED
        result.stopped_at_stage = "ready_for_export"
    return result


def _review_gate_blocks(role_assignment: RoleAssignmentResult) -> bool:
    """REVIEW GATE kuralı (CLAUDE.md §3, §4.1, §4.8):

    Herhangi bir konuşmacı `unresolved`/`unknown`/`review_needed` İSE YA DA
    `manual_review_required=True` İSE pipeline durur. `review_needed` de
    bloke eder — "net değil ama belki yeterli" diye gate'i geçirmek CLAUDE.md
    §4.1'i ("belirsizse tahmin etme") ihlal eder.
    """
    return role_assignment.manual_review_required or role_assignment.requires_role_review


def _continue_after_role_assignment(
    result: PipelineResult,
    speaker_labelled: SpeakerLabelledTranscript,
    role_assignment: RoleAssignmentResult,
    llm_provider: LLMProvider,
) -> PipelineResult:
    """REVIEW GATE geçildikten sonraki tüm aşamalar (facts → note →
    procedures → code matching). Bu aşamaların içerik üretimi STUB'tır.

    `run_pipeline` ve `resume_after_role_review`'ın HER İKİSİ de bu fonksiyona
    delege eder — bu yüzden aşağıdaki `SourceRoleInvariantViolation` yakalama
    mantığı her iki giriş noktası için de geçerlidir.

    `stages._enforce_source_role_invariant`, REVIEW GATE'i bir şekilde atlayıp
    facts'e kadar sızan `source_role=unknown` bir fact bulursa
    `SourceRoleInvariantViolation` fırlatır (bkz. stages.py). Bu BEKLENMEYEN
    bir durumdur (gate doğru çalışıyorsa hiç oluşmaz) ama sessizce yutulmaz:
    pipeline burada durur, hiçbir clinical_note/procedure/kod önerisi
    üretilmeden temiz bir terminal duruma (`NEEDS_DENTIST_ROLE_REVIEW`) geçer
    ve hekim yeniden rol incelemesine yönlendirilir.

    KVKK (CLAUDE.md §5): hem burada hem stages.py'de loglanan/exception'a
    taşınan veri yalnızca `session_id` + `speaker_id` + kategoridir — HAM
    `source_quote` hiçbir noktada loga/exception mesajına yazılmaz.
    """
    role_labelled = stages.apply_dentist_role_correction(speaker_labelled, role_assignment)
    result.role_labelled_transcript = role_labelled

    try:
        facts = _time_pipeline_stage(
            "extract_clinical_facts",
            result.session_id,
            lambda: stages.extract_clinical_facts(role_labelled, llm_provider),
        )
        note, procedures = _run_note_and_chart_parallel(facts, llm_provider, result.session_id)
        code_suggestions = _time_pipeline_stage(
            "match_codes_and_checklist",
            result.session_id,
            lambda: stages.match_codes_and_checklist(procedures, facts, llm_provider),
        )
    except SourceRoleInvariantViolation as exc:
        logger.error(
            "source_role_invariant_violation_caught: session_id=%s speaker=%s category=%s",
            exc.session_id,
            exc.speaker_id,
            exc.category.value,
        )
        result.status = PipelineStatus.NEEDS_DENTIST_ROLE_REVIEW
        result.stopped_at_stage = "facts_extraction_invariant_violation"
        return result

    result.clinical_facts = facts
    result.clinical_note = note
    result.procedures = procedures
    result.code_suggestions = code_suggestions

    result.status = PipelineStatus.AWAITING_DENTIST_REVIEW
    result.stopped_at_stage = "dentist_review"
    return result


def _time_pipeline_stage(stage_name: str, session_id: Optional[str], func):
    started_at = time.time()
    try:
        return func()
    finally:
        duration_sec = time.time() - started_at
        logger.warning(
            "pipeline_timing stage=%s session_id=%s duration_sec=%.3f",
            stage_name,
            session_id or "unknown",
            duration_sec,
        )


def _run_note_and_chart_parallel(facts, llm_provider: LLMProvider, session_id: Optional[str]):
    return asyncio.run(_run_note_and_chart_parallel_async(facts, llm_provider, session_id))


async def _run_note_and_chart_parallel_async(facts, llm_provider: LLMProvider, session_id: Optional[str]):
    return await asyncio.gather(
        asyncio.to_thread(
            _time_pipeline_stage,
            "generate_clinical_note",
            session_id,
            lambda: stages.generate_clinical_note(facts, llm_provider),
        ),
        asyncio.to_thread(
            _time_pipeline_stage,
            "extract_dental_chart_commands",
            session_id,
            lambda: stages.extract_dental_chart_commands(facts, llm_provider),
        ),
    )
