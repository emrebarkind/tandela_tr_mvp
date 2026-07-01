"""Transcript tabanlı pipeline API servisleri.

V1'in gerçek girişi audio olacak; ASR/diarization provider seçimi henüz TBD.
Bu servis, frontend/API entegrasyonunu erkenden kurabilmek için speaker-labelled
transkript üzerinden aynı klinik pipeline kapılarını çalıştırır.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional

from pydantic import BaseModel, Field

from app.pipeline import stages
from app.pipeline.stages import SourceRoleInvariantViolation
from app.pipeline.types import (
    CandidateCode,
    ClinicalNoteDraft,
    CodeExplanation,
    CodeMatchState,
    CodeMatchResult,
    CodeSuggestionBundle,
    DentistRole,
    DentistReviewDecision,
    PipelineResult,
    PipelineStatus,
    ProcedureObject,
    RoleAssignmentResult,
    RoleStatus,
    SpeakerLabelledTranscript,
    SpeakerRoleAssignment,
    Utterance,
)
from app.providers.llm import LLMProvider


class TranscriptUtteranceIn(BaseModel):
    speaker_id: str
    text: str
    start_sec: Optional[float] = None
    end_sec: Optional[float] = None


class RoleCorrectionIn(BaseModel):
    speaker_id: str
    role: DentistRole
    status: RoleStatus = RoleStatus.CLEAR
    reason: Optional[str] = None


class TranscriptAnalyzeRequest(BaseModel):
    session_id: Optional[str] = None
    transcript_text: Optional[str] = None
    utterances: list[TranscriptUtteranceIn] = Field(default_factory=list)


class TranscriptResumeAfterRoleReviewRequest(TranscriptAnalyzeRequest):
    corrected_roles: list[RoleCorrectionIn] = Field(default_factory=list)


class ResumeRoleReviewRequest(BaseModel):
    corrected_roles: list[RoleCorrectionIn] = Field(default_factory=list)
    transcript_text: Optional[str] = None
    utterances: list[TranscriptUtteranceIn] = Field(default_factory=list)


class ApproveReviewRequest(BaseModel):
    session_id: Optional[str] = None
    selected_codes: list[str] = Field(default_factory=list)
    reviewer_user_id: Optional[str] = None
    approved: bool = True
    approved_note: Optional[ClinicalNoteDraft] = None


class SessionState(BaseModel):
    session_id: str
    transcript: SpeakerLabelledTranscript
    result: PipelineResult
    created_at_utc: str
    updated_at_utc: str


class RoleReviewSpeakerOut(BaseModel):
    speaker_id: str
    role: DentistRole
    status: RoleStatus
    review_state: RoleStatus
    utterance_count: int
    reason: Optional[str] = None


class AudioProcessingReviewOut(BaseModel):
    status: str
    raw_audio_deleted: bool
    provider_status: str
    message: str
    warnings: list[str] = Field(default_factory=list)
    transcript: Optional[SpeakerLabelledTranscript] = None


class RoleReviewOut(BaseModel):
    speakers: list[RoleReviewSpeakerOut] = Field(default_factory=list)
    manual_review_required: bool = True


class ProcedureCodeReviewOut(BaseModel):
    procedure: ProcedureObject
    review_state: CodeMatchState
    candidates: list[CandidateCode] = Field(default_factory=list)
    match_results: list[CodeMatchResult] = Field(default_factory=list)
    explanations: list[CodeExplanation] = Field(default_factory=list)
    ambiguity_note: Optional[str] = None
    dentist_must_choose: bool = True


class DentistReviewOut(BaseModel):
    review_state: str = "draft_requires_dentist_approval"
    note: ClinicalNoteDraft
    procedures: list[ProcedureCodeReviewOut] = Field(default_factory=list)
    uncertain_items: list[str] = Field(default_factory=list)


class ExportAuditOut(BaseModel):
    action: str = "doctor_approved_export_payload"
    reviewer_user_id: Optional[str] = None
    approved: bool = True
    created_at_utc: str
    source: str = "frontend_review"


class ExportPayloadOut(BaseModel):
    session_id: str
    clinical_note_text: str
    selected_codes: list[str] = Field(default_factory=list)
    audit: ExportAuditOut
    warning: str = "Taslak çıktı hekim onayıyla hazırlanmıştır; otomatik klinik kayıt değildir."


class PipelineReviewResponse(BaseModel):
    session_id: str
    status: PipelineStatus
    review_state: str
    stopped_at_stage: Optional[str] = None
    next_action: str
    role_review: Optional[RoleReviewOut] = None
    dentist_review: Optional[DentistReviewOut] = None
    export_payload: Optional[ExportPayloadOut] = None
    audio_processing: Optional[AudioProcessingReviewOut] = None


_SESSION_STORE: dict[str, SessionState] = {}


def analyze_transcript(
    request: TranscriptAnalyzeRequest,
    llm_provider: LLMProvider,
) -> PipelineResult:
    """Role assignment'tan başlar; REVIEW GATE bloke ederse facts üretmez."""
    speaker_labelled = _build_speaker_labelled_transcript(request)
    result = PipelineResult(
        session_id=request.session_id,
        status=PipelineStatus.OK,
        speaker_labelled_transcript=speaker_labelled,
    )

    role_assignment = stages.assign_roles(speaker_labelled, llm_provider)
    result.role_assignment = role_assignment

    if _review_gate_blocks(role_assignment):
        result.status = PipelineStatus.NEEDS_DENTIST_ROLE_REVIEW
        result.stopped_at_stage = "role_assignment"
        return result

    return _continue_after_role_assignment(result, speaker_labelled, role_assignment, llm_provider)


def resume_transcript_after_role_review(
    request: TranscriptResumeAfterRoleReviewRequest,
    llm_provider: LLMProvider,
) -> PipelineResult:
    """Hekim rol düzeltmesi/onayı sonrası facts → note → procedure → code akışı."""
    speaker_labelled = _build_speaker_labelled_transcript(request)
    corrected = _build_corrected_role_assignment(request, speaker_labelled)
    result = PipelineResult(
        session_id=request.session_id,
        status=PipelineStatus.OK,
        speaker_labelled_transcript=speaker_labelled,
        role_assignment=corrected,
    )

    if _review_gate_blocks(corrected):
        result.status = PipelineStatus.NEEDS_DENTIST_ROLE_REVIEW
        result.stopped_at_stage = "role_assignment"
        return result

    return _continue_after_role_assignment(result, speaker_labelled, corrected, llm_provider)


def approve_review(request: ApproveReviewRequest) -> PipelineResult:
    """Hekim clinical review onayını API kontratına bağlar.

    Henüz DB/export katmanı yok; bu fonksiyon onayın durum geçişini kurar.
    Kalıcı audit/export eklendiğinde aynı request gövdesiyle kayıt yazılacak.
    """
    result = PipelineResult(
        session_id=request.session_id,
        status=PipelineStatus.AWAITING_DENTIST_REVIEW,
        stopped_at_stage="dentist_review",
    )
    decision = DentistReviewDecision(
        approved=request.approved,
        edited_note=request.approved_note,
        selected_codes=request.selected_codes,
        reviewer_user_id=request.reviewer_user_id,
    )
    if decision.approved:
        result.status = PipelineStatus.APPROVED
        result.clinical_note = request.approved_note
        result.review_decision = decision
        result.stopped_at_stage = "ready_for_export"
    else:
        result.review_decision = decision
    return result


def create_session_from_transcript(
    request: TranscriptAnalyzeRequest,
    llm_provider: LLMProvider,
) -> PipelineResult:
    session_id = request.session_id or f"session-{uuid4().hex[:12]}"
    normalized_request = request.model_copy(update={"session_id": session_id})
    result = analyze_transcript(normalized_request, llm_provider)
    _store_session_result(session_id, result)
    return result


def resume_session_after_role_review(
    session_id: str,
    request: ResumeRoleReviewRequest,
    llm_provider: LLMProvider,
) -> PipelineResult:
    existing = _SESSION_STORE.get(session_id)
    utterances = request.utterances
    transcript_text = request.transcript_text
    if not utterances and transcript_text is None:
        if existing is None:
            raise KeyError(session_id)
        utterances = [
            TranscriptUtteranceIn(
                speaker_id=utterance.speaker_id,
                text=utterance.text,
                start_sec=utterance.start_sec,
                end_sec=utterance.end_sec,
            )
            for utterance in existing.transcript.utterances
        ]

    result = resume_transcript_after_role_review(
        TranscriptResumeAfterRoleReviewRequest(
            session_id=session_id,
            transcript_text=transcript_text,
            utterances=utterances,
            corrected_roles=request.corrected_roles,
        ),
        llm_provider,
    )
    _store_session_result(session_id, result)
    return result


def approve_session_review(
    session_id: str,
    request: ApproveReviewRequest,
) -> PipelineResult:
    existing = _SESSION_STORE.get(session_id)
    if existing is None:
        raise KeyError(session_id)
    if existing.result.status != PipelineStatus.AWAITING_DENTIST_REVIEW:
        raise ValueError("Session hekim review aşamasında değil; onaysız export üretilemez.")

    approved_note = request.approved_note or existing.result.clinical_note
    result = approve_review(
        request.model_copy(
            update={
                "session_id": session_id,
                "approved_note": approved_note,
            }
        )
    )
    result.speaker_labelled_transcript = existing.result.speaker_labelled_transcript
    result.role_assignment = existing.result.role_assignment
    result.role_labelled_transcript = existing.result.role_labelled_transcript
    result.clinical_facts = existing.result.clinical_facts
    result.clinical_note = approved_note
    result.procedures = existing.result.procedures
    result.code_suggestions = existing.result.code_suggestions
    _store_session_result(session_id, result)
    return result


def to_review_response(result: PipelineResult) -> PipelineReviewResponse:
    """PipelineResult'ı frontend review ekranının tükettiği dar DTO'ya çevir."""
    return PipelineReviewResponse(
        session_id=result.session_id,
        status=result.status,
        review_state=_review_state(result.status),
        stopped_at_stage=result.stopped_at_stage,
        next_action=_next_action(result.status),
        role_review=_build_role_review(result),
        dentist_review=_build_dentist_review(result),
        export_payload=_build_export_payload(result),
    )


def _review_state(status: PipelineStatus) -> str:
    if status == PipelineStatus.NEEDS_DENTIST_ROLE_REVIEW:
        return "needs_dentist_role_review"
    if status == PipelineStatus.AWAITING_DENTIST_REVIEW:
        return "draft_requires_dentist_approval"
    if status == PipelineStatus.APPROVED:
        return "approved_ready_for_export"
    if status == PipelineStatus.EXPORTED:
        return "exported"
    return "processing"


def _next_action(status: PipelineStatus) -> str:
    if status == PipelineStatus.NEEDS_DENTIST_ROLE_REVIEW:
        return "review_speaker_roles"
    if status == PipelineStatus.AWAITING_DENTIST_REVIEW:
        return "review_note_and_codes"
    if status == PipelineStatus.APPROVED:
        return "export"
    if status == PipelineStatus.EXPORTED:
        return "done"
    return "wait"


def _build_role_review(result: PipelineResult) -> Optional[RoleReviewOut]:
    if result.status != PipelineStatus.NEEDS_DENTIST_ROLE_REVIEW or result.role_assignment is None:
        return None
    return RoleReviewOut(
        speakers=[
            RoleReviewSpeakerOut(
                speaker_id=assignment.speaker_id,
                role=assignment.role,
                status=assignment.status,
                review_state=assignment.status,
                utterance_count=assignment.utterance_count,
                reason=assignment.reason,
            )
            for assignment in result.role_assignment.assignments
        ],
        manual_review_required=result.role_assignment.manual_review_required,
    )


def _build_dentist_review(result: PipelineResult) -> Optional[DentistReviewOut]:
    if result.status != PipelineStatus.AWAITING_DENTIST_REVIEW or result.clinical_note is None:
        return None

    bundles_by_index: dict[int, CodeSuggestionBundle] = {
        idx: bundle for idx, bundle in enumerate(result.code_suggestions)
    }
    procedure_reviews = []
    for idx, procedure in enumerate(result.procedures):
        bundle = bundles_by_index.get(idx)
        review_state = (
            bundle.match_results[0].match_state
            if bundle is not None and bundle.match_results
            else CodeMatchState.NO_MATCH
        )
        procedure_reviews.append(
            ProcedureCodeReviewOut(
                procedure=procedure,
                review_state=review_state,
                candidates=bundle.candidates if bundle is not None else [],
                match_results=bundle.match_results if bundle is not None else [],
                explanations=bundle.explanations if bundle is not None else [],
                ambiguity_note=bundle.ambiguity_note if bundle is not None else None,
                dentist_must_choose=bundle.dentist_must_choose if bundle is not None else True,
            )
        )

    uncertain_items = []
    if result.clinical_facts is not None:
        uncertain_items.extend(result.clinical_facts.uncertain_items)
    uncertain_items.extend(
        item for item in result.clinical_note.uncertain_items if item not in uncertain_items
    )
    return DentistReviewOut(
        note=result.clinical_note,
        procedures=procedure_reviews,
        uncertain_items=uncertain_items,
    )


def _build_export_payload(result: PipelineResult) -> Optional[ExportPayloadOut]:
    decision = result.review_decision
    if result.status != PipelineStatus.APPROVED or decision is None or not decision.approved:
        return None

    note = decision.edited_note or result.clinical_note
    return ExportPayloadOut(
        session_id=result.session_id,
        clinical_note_text=_format_note_for_export(note),
        selected_codes=decision.selected_codes,
        audit=ExportAuditOut(
            reviewer_user_id=decision.reviewer_user_id,
            approved=decision.approved,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
        ),
    )


def _format_note_for_export(note: Optional[ClinicalNoteDraft]) -> str:
    if note is None:
        return ""

    sections = [
        ("Hasta şikayeti", note.patient_complaint),
        ("Geçmiş", note.history),
        ("Klinik bulgular", note.clinical_findings),
        ("Değerlendirme", note.assessment),
        ("Tedavi planı", note.treatment_plan),
        ("İşlem notu", note.procedures_note),
    ]
    lines: list[str] = []
    for title, sentences in sections:
        if not sentences:
            continue
        lines.append(title)
        lines.extend(f"- {sentence.text}" for sentence in sentences)
        lines.append("")
    if note.uncertain_items:
        lines.append("Belirsiz / hekim review maddeleri")
        lines.extend(f"- {item}" for item in note.uncertain_items)
        lines.append("")
    return "\n".join(lines).strip()


def _build_speaker_labelled_transcript(
    request: TranscriptAnalyzeRequest,
) -> SpeakerLabelledTranscript:
    session_id = request.session_id or f"session-{uuid4().hex[:12]}"
    input_utterances = request.utterances or _parse_transcript_text(request.transcript_text)
    if not input_utterances:
        raise ValueError("Transkript boş olamaz.")

    utterances = []
    for idx, item in enumerate(input_utterances):
        start_sec = item.start_sec if item.start_sec is not None else float(idx)
        end_sec = item.end_sec if item.end_sec is not None else start_sec + 1.0
        utterances.append(
            Utterance(
                speaker_id=item.speaker_id,
                text=item.text,
                start_sec=start_sec,
                end_sec=end_sec,
            )
        )
    return SpeakerLabelledTranscript(session_id=session_id, utterances=utterances)


def _parse_transcript_text(transcript_text: Optional[str]) -> list[TranscriptUtteranceIn]:
    if not transcript_text:
        return []

    parsed: list[TranscriptUtteranceIn] = []
    plain_lines: list[str] = []
    for raw_line in transcript_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" in line:
            speaker_id, text = line.split(":", 1)
            speaker_id = speaker_id.strip()
            text = text.strip()
            if speaker_id and text:
                parsed.append(TranscriptUtteranceIn(speaker_id=speaker_id, text=text))
                continue
        plain_lines.append(line)

    if parsed and not plain_lines:
        return parsed
    if parsed and plain_lines:
        parsed.extend(TranscriptUtteranceIn(speaker_id="A", text=line) for line in plain_lines)
        return parsed

    # Düz metin diarization bilgisi taşımaz; tek nötr konuşmacı olarak verilir.
    # REVIEW GATE bu belirsizliği hekim rol onayına taşıyabilir.
    return [TranscriptUtteranceIn(speaker_id="A", text=" ".join(plain_lines))]


def _build_corrected_role_assignment(
    request: TranscriptResumeAfterRoleReviewRequest,
    transcript: SpeakerLabelledTranscript,
) -> RoleAssignmentResult:
    counts: dict[str, int] = {}
    for utterance in transcript.utterances:
        counts[utterance.speaker_id] = counts.get(utterance.speaker_id, 0) + 1

    speaker_ids = set(counts.keys())
    corrected_by_speaker = {item.speaker_id: item for item in request.corrected_roles}
    if set(corrected_by_speaker.keys()) != speaker_ids:
        assignments = [
            SpeakerRoleAssignment(
                speaker_id=sid,
                role=corrected_by_speaker[sid].role if sid in corrected_by_speaker else DentistRole.UNKNOWN,
                status=corrected_by_speaker[sid].status if sid in corrected_by_speaker else RoleStatus.UNRESOLVED,
                utterance_count=counts[sid],
                reason=(
                    corrected_by_speaker[sid].reason
                    if sid in corrected_by_speaker and corrected_by_speaker[sid].reason
                    else "Rol düzeltmesi transcript konuşmacılarıyla birebir eşleşmedi."
                ),
            )
            for sid in sorted(speaker_ids)
        ]
        return RoleAssignmentResult(
            session_id=request.session_id or transcript.session_id,
            assignments=assignments,
            manual_review_required=True,
        )

    assignments = [
        SpeakerRoleAssignment(
            speaker_id=sid,
            role=corrected_by_speaker[sid].role,
            status=corrected_by_speaker[sid].status,
            utterance_count=counts[sid],
            reason=corrected_by_speaker[sid].reason or "Hekim role review sonrası onayladı.",
        )
        for sid in sorted(speaker_ids)
    ]

    return RoleAssignmentResult(
        session_id=request.session_id or transcript.session_id,
        assignments=assignments,
        manual_review_required=False,
    )


def _store_session_result(session_id: str, result: PipelineResult) -> None:
    transcript = result.speaker_labelled_transcript
    if transcript is None:
        existing = _SESSION_STORE.get(session_id)
        if existing is None:
            return
        transcript = existing.transcript
    now = datetime.now(timezone.utc).isoformat()
    existing = _SESSION_STORE.get(session_id)
    _SESSION_STORE[session_id] = SessionState(
        session_id=session_id,
        transcript=transcript,
        result=result,
        created_at_utc=existing.created_at_utc if existing is not None else now,
        updated_at_utc=now,
    )


def _review_gate_blocks(role_assignment: RoleAssignmentResult) -> bool:
    return role_assignment.manual_review_required or role_assignment.requires_role_review


def _continue_after_role_assignment(
    result: PipelineResult,
    speaker_labelled: SpeakerLabelledTranscript,
    role_assignment: RoleAssignmentResult,
    llm_provider: LLMProvider,
) -> PipelineResult:
    role_labelled = stages.apply_dentist_role_correction(speaker_labelled, role_assignment)
    result.role_labelled_transcript = role_labelled

    try:
        facts = stages.extract_clinical_facts(role_labelled, llm_provider)
        note = stages.generate_clinical_note(facts, llm_provider)
        procedures = stages.extract_dental_chart_commands(facts, llm_provider)
        code_suggestions = stages.match_codes_and_checklist(procedures, facts, llm_provider)
    except SourceRoleInvariantViolation:
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
