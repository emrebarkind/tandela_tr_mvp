"""Transcript tabanlı pipeline API servisleri.

V1'in gerçek girişi audio olacak; ASR/diarization provider seçimi henüz TBD.
Bu servis, frontend/API entegrasyonunu erkenden kurabilmek için speaker-labelled
transkript üzerinden aynı klinik pipeline kapılarını çalıştırır.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Optional
from uuid import uuid4

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
    DentalCondition,
    derive_fdi_classification,
    DentistRole,
    DentistReviewDecision,
    is_valid_fdi_number,
    PipelineResult,
    PipelineStatus,
    ProcedureObject,
    ProcedureStatus,
    RoleAssignmentResult,
    RoleStatus,
    SpeakerLabelledTranscript,
    SpeakerRoleAssignment,
    Utterance,
)
from app.providers.llm import LLMProvider


logger = logging.getLogger(__name__)


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
    patient_id: Optional[str] = None
    transcript_text: Optional[str] = None
    utterances: list[TranscriptUtteranceIn] = Field(default_factory=list)


class TranscriptResumeAfterRoleReviewRequest(TranscriptAnalyzeRequest):
    corrected_roles: list[RoleCorrectionIn] = Field(default_factory=list)


class ResumeRoleReviewRequest(BaseModel):
    corrected_roles: list[RoleCorrectionIn] = Field(default_factory=list)
    transcript_text: Optional[str] = None
    utterances: list[TranscriptUtteranceIn] = Field(default_factory=list)


class SpeakerRolePatchRequest(BaseModel):
    speaker_id: str
    role: DentistRole
    reason: Optional[str] = None


class ManualFindingRequest(BaseModel):
    tooth_number_fdi: int
    condition: DentalCondition
    note: Optional[str] = None


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


class UncertainSpeakerOut(BaseModel):
    speaker_id: str
    tentative_role: DentistRole
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
    role_review_required: bool = False
    uncertain_speakers: list[UncertainSpeakerOut] = Field(default_factory=list)
    role_review: Optional[RoleReviewOut] = None
    dentist_review: Optional[DentistReviewOut] = None
    export_payload: Optional[ExportPayloadOut] = None
    audio_processing: Optional[AudioProcessingReviewOut] = None


_SESSION_STORE: dict[str, SessionState] = {}


def restore_session_result(result: PipelineResult) -> None:
    """Rehydrate transient workflow state from the clinic-scoped DB snapshot."""
    _store_session_result(result.session_id, result)


def analyze_transcript(
    request: TranscriptAnalyzeRequest,
    llm_provider: LLMProvider,
) -> PipelineResult:
    """Role assignment'tan başlar; belirsiz rolleri draft metadata'sı olarak taşır."""
    speaker_labelled = _build_speaker_labelled_transcript(request)
    result = PipelineResult(
        session_id=request.session_id,
        status=PipelineStatus.OK,
        speaker_labelled_transcript=speaker_labelled,
    )

    role_assignment = _time_pipeline_stage(
        "assign_roles",
        result.session_id,
        lambda: stages.assign_roles(speaker_labelled, llm_provider),
    )
    result.role_assignment = role_assignment

    return _continue_after_role_assignment(
        result,
        speaker_labelled,
        _execution_role_assignment(role_assignment, speaker_labelled),
        llm_provider,
        review_role_assignment=role_assignment,
    )


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

    return _continue_after_role_assignment(
        result,
        speaker_labelled,
        _execution_role_assignment(corrected, speaker_labelled),
        llm_provider,
        review_role_assignment=corrected,
    )


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


def patch_session_speaker_role(
    session_id: str,
    request: SpeakerRolePatchRequest,
    llm_provider: LLMProvider,
) -> PipelineResult:
    existing = _SESSION_STORE.get(session_id)
    if existing is None:
        raise KeyError(session_id)
    if existing.result.role_assignment is None:
        raise ValueError("Session rol ataması içermiyor.")

    speaker_ids = {utterance.speaker_id for utterance in existing.transcript.utterances}
    if request.speaker_id not in speaker_ids:
        raise ValueError("Konuşmacı bu session transkriptinde bulunamadı.")

    corrected_roles = []
    for assignment in existing.result.role_assignment.assignments:
        role = request.role if assignment.speaker_id == request.speaker_id else assignment.role
        corrected_roles.append(
            RoleCorrectionIn(
                speaker_id=assignment.speaker_id,
                role=role,
                status=RoleStatus.CLEAR,
                reason=(
                    request.reason
                    if assignment.speaker_id == request.speaker_id and request.reason
                    else "Frontend inline rol düzeltmesi."
                ),
            )
        )

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
            utterances=utterances,
            corrected_roles=corrected_roles,
        ),
        llm_provider,
    )
    _store_session_result(session_id, result)
    return result


def add_manual_finding_to_session(
    session_id: str,
    request: ManualFindingRequest,
) -> PipelineResult:
    existing = _SESSION_STORE.get(session_id)
    if existing is None:
        raise KeyError(session_id)
    if existing.result.status != PipelineStatus.AWAITING_DENTIST_REVIEW:
        raise ValueError("Manuel bulgu yalnızca hekim review aşamasındaki taslağa eklenebilir.")
    if not is_valid_fdi_number(request.tooth_number_fdi):
        raise ValueError("FDI diş numarası geçerli değil.")

    dentition, tooth_type, tooth_group = derive_fdi_classification(request.tooth_number_fdi)
    note = request.note.strip() if request.note else ""
    source_quote = note or "Hekim tarafından manuel eklendi"
    procedure = ProcedureObject(
        procedure_family=_manual_condition_family(request.condition),
        tooth_number_fdi=request.tooth_number_fdi,
        dentition=dentition,
        tooth_type=tooth_type,
        tooth_group=tooth_group,
        condition=request.condition,
        status=ProcedureStatus.PERFORMED,
        source_quotes=[source_quote],
        source_role=DentistRole.DENTIST,
        is_manual=True,
        manual_note=note or None,
    )
    result = existing.result.model_copy(
        update={
            "procedures": [*existing.result.procedures, procedure],
            "status": PipelineStatus.AWAITING_DENTIST_REVIEW,
            "stopped_at_stage": "dentist_review",
        }
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
        role_review_required=_role_review_required(result),
        uncertain_speakers=_build_uncertain_speakers(result),
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


def _role_review_required(result: PipelineResult) -> bool:
    return result.role_assignment is not None and _review_gate_blocks(result.role_assignment)


def _build_uncertain_speakers(result: PipelineResult) -> list[UncertainSpeakerOut]:
    if result.role_assignment is None:
        return []
    return [
        UncertainSpeakerOut(
            speaker_id=assignment.speaker_id,
            tentative_role=assignment.role,
            reason=assignment.reason,
        )
        for assignment in result.role_assignment.assignments
        if _assignment_needs_review(assignment)
    ]


def _build_role_review(result: PipelineResult) -> Optional[RoleReviewOut]:
    if result.role_assignment is None or not _review_gate_blocks(result.role_assignment):
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

    lines: list[str] = []
    patient_fields = [
        ("Ad / Soyad", note.patient_information.display_name),
        ("Yaş", note.patient_information.age),
        ("T.C. Kimlik No", note.patient_information.national_id),
        ("Doğum tarihi", note.patient_information.date_of_birth),
        ("Meslek", note.patient_information.occupation),
        ("Adres", note.patient_information.address),
        ("Telefon", note.patient_information.phone),
        ("E-posta", note.patient_information.email),
        ("Yönlendiren", note.patient_information.referred_by),
    ]
    if any(field is not None for _, field in patient_fields):
        lines.append("Hasta Bilgileri")
        lines.extend(f"- {label}: {field.value}" for label, field in patient_fields if field is not None)
        lines.append("")

    medical_fields = [
        ("Kronik hastalık", note.medical_history.chronic_illness),
        ("Düzenli ilaç", note.medical_history.regular_medication),
        ("İlaç alerjisi", note.medical_history.drug_allergy),
        ("Bulaşıcı hastalık", note.medical_history.contagious_disease),
    ]
    if any(field is not None for _, field in medical_fields):
        lines.append("Tıbbi Özgeçmiş")
        for label, field in medical_fields:
            if field is None:
                continue
            answer = "Var / Evet" if field.value is True else "Yok / Hayır" if field.value is False else "Belirsiz"
            detail = f" — {field.detail}" if field.detail else ""
            lines.append(f"- {label}: {answer}{detail}")
        lines.append("")

    sections = [
        ("Hasta şikayeti", note.patient_complaint),
        ("Geçmiş", note.history),
        ("Klinik bulgular", note.clinical_findings),
        ("Değerlendirme", note.assessment),
        ("Tedavi planı", note.treatment_plan),
        ("İşlem notu", note.procedures_note),
    ]
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


def _assignment_needs_review(assignment: SpeakerRoleAssignment) -> bool:
    return (
        assignment.status in (RoleStatus.UNRESOLVED, RoleStatus.REVIEW_NEEDED)
        or assignment.role == DentistRole.UNKNOWN
    )


def _execution_role_assignment(
    role_assignment: RoleAssignmentResult,
    transcript: SpeakerLabelledTranscript,
) -> RoleAssignmentResult:
    """Create a safe tentative role map for draft generation.

    The original role assignment remains on PipelineResult for UI review
    metadata. This execution copy only prevents the draft pipeline from being
    blocked by a role-review banner. If a role is unresolved, use explicit
    utterance-language cues to choose a tentative role:
    - dentist-like clinical action/documentation language -> dentist
    - patient symptom/question language -> patient
    - otherwise -> assistant_or_other

    The UI still receives role_review_required=true from the original result, so
    the clinician remains the final authority.
    """
    utterances_by_speaker: dict[str, list[str]] = {}
    for utterance in transcript.utterances:
        utterances_by_speaker.setdefault(utterance.speaker_id, []).append(utterance.text)

    assignments = []
    for assignment in role_assignment.assignments:
        if _assignment_needs_review(assignment):
            role = _tentative_role_from_utterances(
                utterances_by_speaker.get(assignment.speaker_id, [])
            )
            assignments.append(
                assignment.model_copy(update={"role": role, "status": assignment.status})
            )
            continue
        assignments.append(assignment)
    return role_assignment.model_copy(update={"assignments": assignments})


def _tentative_role_from_utterances(utterances: list[str]) -> DentistRole:
    text = " ".join(utterances).casefold().replace("i̇", "i")
    dentist_markers = (
        "ağzınızı aç",
        "agzinizi ac",
        "görüyorum",
        "goruyorum",
        "röntgen",
        "rontgen",
        "perküsyon",
        "perkusyon",
        "planlandı",
        "planlandi",
        "planlayalım",
        "planlayalim",
        "yapılacak",
        "yapilacak",
        "kanal tedavisi",
        "geçici restorasyon",
        "gecici restorasyon",
        "geçici dolgu",
        "gecici dolgu",
        "kompozit dolgu var",
        "muayene",
    )
    patient_markers = (
        "ağrım",
        "agrim",
        "şikayet",
        "sikayet",
        "hassasiyetim",
        "benim dişim",
        "benim disim",
        "dişimi",
        "disimi",
        "yani",
        "mi?",
        "değil mi",
        "degil mi",
    )
    if any(marker in text for marker in dentist_markers):
        return DentistRole.DENTIST
    if any(marker in text for marker in patient_markers):
        return DentistRole.PATIENT
    return DentistRole.ASSISTANT_OR_OTHER


def _manual_condition_family(condition: DentalCondition) -> str:
    if condition == DentalCondition.RCT:
        return "kanal_tedavisi"
    if condition == DentalCondition.COMPOSITE:
        return "kompozit_dolgu"
    if condition == DentalCondition.MISSING:
        return "dis_cekimi"
    return "manuel_bulgu"


def _continue_after_role_assignment(
    result: PipelineResult,
    speaker_labelled: SpeakerLabelledTranscript,
    role_assignment: RoleAssignmentResult,
    llm_provider: LLMProvider,
    review_role_assignment: Optional[RoleAssignmentResult] = None,
) -> PipelineResult:
    role_labelled = stages.apply_dentist_role_correction(speaker_labelled, role_assignment)
    result.role_labelled_transcript = role_labelled

    try:
        facts = _time_pipeline_stage(
            "extract_clinical_facts",
            result.session_id,
            lambda: stages.extract_clinical_facts(role_labelled, llm_provider),
        )
        facts = _mark_source_role_confidence(facts, review_role_assignment or role_assignment)
        note, procedures = _run_note_and_chart_parallel(facts, llm_provider, result.session_id)
        code_suggestions = _time_pipeline_stage(
            "match_codes_and_checklist",
            result.session_id,
            lambda: stages.match_codes_and_checklist(procedures, facts, llm_provider),
        )
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


def _mark_source_role_confidence(
    facts,
    role_assignment: RoleAssignmentResult,
):
    uncertain_speakers = {
        assignment.speaker_id
        for assignment in role_assignment.assignments
        if _assignment_needs_review(assignment)
    }
    marked_facts = [
        fact.model_copy(
            update={
                "source_role_confidence": (
                    "uncertain" if fact.source_speaker in uncertain_speakers else "clear"
                )
            }
        )
        for fact in facts.facts
    ]
    return facts.model_copy(update={"facts": marked_facts})
