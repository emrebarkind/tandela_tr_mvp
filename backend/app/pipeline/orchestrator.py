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

import logging

from app.pipeline import stages
from app.pipeline.stages import SourceRoleInvariantViolation
from app.pipeline.types import (
    AudioRef,
    DentistReviewDecision,
    PipelineResult,
    PipelineStatus,
    RoleAssignmentResult,
    SpeakerLabelledTranscript,
)
from app.providers.audio_processing import AudioProcessingProvider
from app.providers.llm import LLMProvider

logger = logging.getLogger(__name__)


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

    role_assignment = stages.assign_roles(speaker_labelled, llm_provider)
    result.role_assignment = role_assignment

    if _review_gate_blocks(role_assignment):
        result.status = PipelineStatus.NEEDS_DENTIST_ROLE_REVIEW
        result.stopped_at_stage = "role_assignment"
        return result

    return _continue_after_role_assignment(result, speaker_labelled, role_assignment)


def resume_after_role_review(
    result: PipelineResult,
    speaker_labelled: SpeakerLabelledTranscript,
    corrected_role_assignment: RoleAssignmentResult,
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

    return _continue_after_role_assignment(result, speaker_labelled, corrected_role_assignment)


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
        facts = stages.extract_clinical_facts(role_labelled)
        note = stages.generate_clinical_note(facts)
        procedures = stages.extract_procedures(facts)
        code_suggestions = stages.match_codes_and_checklist(procedures)
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
