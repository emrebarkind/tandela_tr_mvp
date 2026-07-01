"""
Pipeline'in her aşaması arasında geçen veri tipleri.

Bunlar GERÇEK tiplerdir — pipeline'in kendisi stub olsa da (henüz gerçek
ASR/LLM/DB çağrısı yok), veri sözleşmeleri CLAUDE.md ve
docs/tdb-code-matching-spec.md ile birebir uyumlu tanımlanmıştır. İleride
somut implementasyonlar bu tipleri olduğu gibi kullanır; alan eklemek
gerekirse buradan eklenir, ad/anlam değişmez.

Kapsam dışı (bilinçli): SQLAlchemy DB modelleri burada DEĞİL — onlar
backend/app/models/ altında, kalıcı depolama için ayrı bir kaygı. Bu dosya
yalnızca pipeline'in bellek-içi (in-memory) veri akışını tanımlar.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Ortak durum etiketleri (CLAUDE.md §4.7 — sayısal confidence UI'da YASAK,
# her yerde durum etiketi kullanılır)
# ---------------------------------------------------------------------------


class RoleStatus(str, Enum):
    CLEAR = "clear"
    REVIEW_NEEDED = "review_needed"
    UNRESOLVED = "unresolved"


class ChecklistItemStatus(str, Enum):
    FOUND = "found"
    REVIEW = "review"
    MISSING = "missing"


class CodeMatchState(str, Enum):
    CONFIRMED_BY_DOCUMENTATION = "confirmed_by_documentation"
    NEEDS_REVIEW = "needs_review"
    INSUFFICIENT_DOCUMENTATION = "insufficient_documentation"
    AMBIGUOUS_MULTIPLE_CANDIDATES = "ambiguous_multiple_candidates"
    NO_MATCH = "no_match"


class DentistRole(str, Enum):
    DENTIST = "dentist"
    PATIENT = "patient"
    ASSISTANT_OR_OTHER = "assistant_or_other"
    UNKNOWN = "unknown"


class ProcedureStatus(str, Enum):
    """docs/tdb-code-matching-spec.md ile hizalı (checklist `status` alanı,
    örn. "İşlem durumu (yapıldı/planlandı)"). Dört değer — sadece
    yapıldı/planlandı değil, "konuşuldu ama ne yapıldığı ne planlandığı net
    değil" durumu da ayrı tutulur; bu UNCLEAR'a sıkıştırılmaz çünkü UNCLEAR
    "transkriptten hiç anlaşılmıyor" anlamına gelir, DISCUSSED ise "konuşma
    geçti ama net bir karar/işlem yok" anlamına gelir — ikisi aynı şey değil
    (CLAUDE.md §4.1/§4.4: epistemik belirsizlik türleri ayrıştırılır)."""

    PERFORMED = "performed"
    PLANNED = "planned"
    DISCUSSED = "discussed"
    UNCLEAR = "unclear"


class FactCategory(str, Enum):
    PATIENT_COMPLAINT = "patient_complaint"
    HISTORY = "history"
    CLINICAL_FINDINGS = "clinical_findings"
    PROCEDURES = "procedures"
    TREATMENT_PLAN = "treatment_plan"
    ASSESSMENT = "assessment"


# ---------------------------------------------------------------------------
# Audio capture / preprocessing
# ---------------------------------------------------------------------------


class AudioRef(BaseModel):
    """İşlenecek sese referans.

    Ham ses kalıcı saklanmaz (KVKK, CLAUDE.md §5) — bu yüzden burada dosya
    içeriği değil, geçici depo referansı tutulur. Pipeline biter bitmez bu
    referansın işaret ettiği kayıt otomatik silinir (retry için sert üst
    sınır: CLAUDE.md §10).
    """

    session_id: str
    storage_uri: str
    duration_sec: Optional[float] = None
    sample_rate_hz: Optional[int] = None


class PreprocessedAudio(BaseModel):
    session_id: str
    storage_uri: str
    normalized: bool = True
    duration_sec: Optional[float] = None


# ---------------------------------------------------------------------------
# ASR / diarization / alignment (AudioProcessingProvider çıktıları)
# ---------------------------------------------------------------------------


class Word(BaseModel):
    text: str
    start_sec: float
    end_sec: float


class Transcript(BaseModel):
    """ASR çıktısı — word-level timestamp'li."""

    session_id: str
    language: str = "tr"
    words: list[Word] = Field(default_factory=list)


class SpeakerSegment(BaseModel):
    speaker_id: str  # "A" / "B" / "C" ... — henüz rol değil, nötr etiket
    start_sec: float
    end_sec: float


class SpeakerSegments(BaseModel):
    """Diarization çıktısı."""

    session_id: str
    segments: list[SpeakerSegment] = Field(default_factory=list)


class Utterance(BaseModel):
    speaker_id: str
    text: str
    start_sec: float
    end_sec: float
    words: list[Word] = Field(default_factory=list)


class SpeakerLabelledTranscript(BaseModel):
    """Alignment çıktısı — ASR + diarization hizalanmış hâli.

    Henüz ROL ataması yok; speaker_id'ler hâlâ "A"/"B"/"C" gibi nötr
    etiketler. Rol ataması bir sonraki aşamada (role_assignment) yapılır.
    """

    session_id: str
    utterances: list[Utterance] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Role assignment + REVIEW GATE (CLAUDE.md §3, §4.1, §4.8)
# ---------------------------------------------------------------------------


class SpeakerRoleAssignment(BaseModel):
    speaker_id: str
    role: DentistRole
    status: RoleStatus
    utterance_count: int = 0
    reason: Optional[str] = None  # unresolved/review_needed ise neden (varsa)


class RoleAssignmentResult(BaseModel):
    session_id: str
    assignments: list[SpeakerRoleAssignment] = Field(default_factory=list)
    manual_review_required: bool = False

    @property
    def requires_role_review(self) -> bool:
        """REVIEW GATE'in kontrol ettiği koşullardan biri.

        Herhangi bir konuşmacının statüsü `unresolved` İSE YA DA rolü
        `unknown` İSE YA DA statüsü `review_needed` İSE True döner.
        `review_needed` de bir belirsizlik türüdür (CLAUDE.md §4.1:
        "Belirsizse tahmin etme" — "review_needed" zaten "net değil, hekim
        baksın" anlamına gelir; gate'i geçmesine izin vermek bu kuralı
        ihlal eder). Sadece `clear` statüsündeki VE rolü `unknown` olmayan
        konuşmacılar bu kontrolden geçer.
        """
        return any(
            a.status in (RoleStatus.UNRESOLVED, RoleStatus.REVIEW_NEEDED)
            or a.role == DentistRole.UNKNOWN
            for a in self.assignments
        )


class RoleLabelledUtterance(BaseModel):
    # `speaker_id` rol ataması SONRASI bile saklanır: `ClinicalFact.source_speaker`
    # (clinical_facts_extraction aşaması) zorunlu bir provenance alanıdır ve bu
    # diarization speaker_id'sine ihtiyaç duyar — rol tek başına yeterli değildir
    # (iki konuşmacı aynı role sahip olabilir, örn. iki "assistant_or_other").
    speaker_id: str
    role: DentistRole
    text: str
    start_sec: float
    end_sec: float


class RoleLabelledTranscript(BaseModel):
    """REVIEW GATE'i geçtikten SONRA üretilir — speaker_id yerine rol var."""

    session_id: str
    utterances: list[RoleLabelledUtterance] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Clinical facts extraction (CLAUDE.md §4.1–§4.4, §4.6, §4.9)
# ---------------------------------------------------------------------------


class ClinicalFact(BaseModel):
    category: FactCategory
    text: str
    source_quote: str  # transkriptten birebir; aşama 2→3'te kaybolmaz/değişmez
    # ZORUNLU provenance — extraction prompt sözleşmesi: her fact source_role +
    # source_speaker + source_quote taşır (Optional DEĞİL; provenance'sız fact yok).
    source_role: DentistRole
    source_speaker: str  # diarization speaker_id (örn. "A"/"B"), rol ataması SONRASI bile saklanır
    tooth_number_fdi: Optional[int] = None  # doğrulanmış FDI (11–48), yoksa None
    status: Optional[ProcedureStatus] = None
    is_uncertain: bool = False  # "şüpheli/gerekebilir/olabilir" → True, asla kesinleştirilmez


class ClinicalFactsBundle(BaseModel):
    session_id: str
    facts: list[ClinicalFact] = Field(default_factory=list)
    uncertain_items: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Clinical note generation — yalnızca fact JSON'undan, yeni bilgi yok
# ---------------------------------------------------------------------------


class NoteSentence(BaseModel):
    """Notun bir bölümündeki tek cümle + provenance.

    CLAUDE.md aşama 2→3 kontratı: `source_quote` ve `source_role`
    transkript→fact→not boyunca TAŞINIR, PARAPHRASE EDİLMEZ. `text` bir
    fact'in `text` alanından gelir (yeniden yazılmaz); `source_quote` o
    fact'in `source_quote`'u ile birebir aynı kalır.
    """

    sentence_id: str
    text: str
    source_role: DentistRole
    source_quote: str


class ClinicalNoteDraft(BaseModel):
    session_id: str
    patient_complaint: list[NoteSentence] = Field(default_factory=list)
    history: list[NoteSentence] = Field(default_factory=list)
    clinical_findings: list[NoteSentence] = Field(default_factory=list)
    assessment: list[NoteSentence] = Field(default_factory=list)
    treatment_plan: list[NoteSentence] = Field(default_factory=list)
    procedures_note: list[NoteSentence] = Field(default_factory=list)
    uncertain_items: list[str] = Field(default_factory=list)
    is_draft: bool = True  # CLAUDE.md §4.10 — her şey taslaktır


# ---------------------------------------------------------------------------
# Procedure extraction
# ---------------------------------------------------------------------------


class SurfaceCount(str, Enum):
    ONE_SURFACE = "one_surface"
    TWO_SURFACE = "two_surface"
    THREE_SURFACE = "three_surface"
    UNCLEAR = "unclear"


class ToothSurface(str, Enum):
    OCCLUSAL = "O"
    MESIAL = "M"
    DISTAL = "D"
    VESTIBULAR = "V"
    LINGUAL = "L"


class DentalCondition(str, Enum):
    CARIES = "caries"
    COMPOSITE = "composite"
    AMALGAM = "amalgam"
    INLAY = "inlay"
    ONLAY = "onlay"
    CROWN = "crown"
    BRIDGE = "bridge"
    PROSTHESIS = "prosthesis"
    IMPLANT = "implant"
    RCT = "rct"
    MISSING = "missing"


class CanalCount(str, Enum):
    ONE_CANAL = "one_canal"
    TWO_CANAL = "two_canal"
    THREE_CANAL = "three_canal"
    UNCLEAR = "unclear"


class ProcedureObject(BaseModel):
    procedure_family: str  # örn. "kompozit_dolgu", "kanal_tedavisi", "dis_cekimi"
    tooth_number_fdi: Optional[int] = None  # doğrulanmış FDI, yoksa None (mırıltıdan üretilmez)
    surface_count: Optional[SurfaceCount] = None
    surfaces: list[ToothSurface] = Field(default_factory=list)
    condition: Optional[DentalCondition] = None
    canal_count: Optional[CanalCount] = None
    status: ProcedureStatus = ProcedureStatus.UNCLEAR
    source_quotes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# TDB code matching + checklist (bkz. docs/tdb-code-matching-spec.md)
# ---------------------------------------------------------------------------


class CandidateCode(BaseModel):
    """Katman A kaydının pipeline'a yansıyan alt kümesi.

    `code`/`procedure_name` deterministik, kapalı TDB DB'sinden gelir — LLM
    bu alanları üretemez/değiştiremez (CLAUDE.md §4.5).
    """

    code: str
    procedure_name: str
    category: str
    source: str = "TDB 2026 Rehber Tarife"
    source_version: str = "2026"
    report_required: bool = False


class ChecklistItemResult(BaseModel):
    item_id: str
    label: str
    status: ChecklistItemStatus
    evidence_quote: Optional[str] = None
    # suggested_wording YALNIZCA transkriptten türetilir; yoksa None (uydurma yok)
    suggested_wording: Optional[str] = None
    suggested_wording_source: Optional[str] = None


class CodeMatchResult(BaseModel):
    code: str
    checklist: list[ChecklistItemResult] = Field(default_factory=list)
    match_state: CodeMatchState


class CodeExplanation(BaseModel):
    """LLM açıklama katmanı çıktısı — kod SEÇMEZ, sadece açıklar (CLAUDE.md §4.5)."""

    code: str
    fit_reason: str
    caveat: Optional[str] = None


class CodeSuggestionBundle(BaseModel):
    """Tek bir extracted procedure için eşleştirme pipeline'ının tam çıktısı."""

    session_id: str
    candidates: list[CandidateCode] = Field(default_factory=list)
    match_results: list[CodeMatchResult] = Field(default_factory=list)
    explanations: list[CodeExplanation] = Field(default_factory=list)
    ambiguity_note: Optional[str] = None
    dentist_must_choose: bool = True


# ---------------------------------------------------------------------------
# Hekim review / approve / export
# ---------------------------------------------------------------------------


class DentistReviewDecision(BaseModel):
    approved: bool = False
    edited_note: Optional[ClinicalNoteDraft] = None
    selected_codes: list[str] = Field(default_factory=list)
    reviewer_user_id: Optional[str] = None


class ExportResult(BaseModel):
    session_id: str
    exported: bool = False
    export_format: Optional[str] = None
    exported_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Pipeline orkestrasyon durumu
# ---------------------------------------------------------------------------


class PipelineStatus(str, Enum):
    OK = "ok"
    NEEDS_DENTIST_ROLE_REVIEW = "needs_dentist_role_review"  # REVIEW GATE durdurdu
    AWAITING_DENTIST_REVIEW = "awaiting_dentist_review"  # not/kod üretildi, hekim onayı bekliyor
    APPROVED = "approved"  # hekim onayladı (decision.approved=True), export ÖNCESİ terminal durum
    EXPORTED = "exported"  # export işlemi gerçekleşti (bu görevin kapsamı dışı — gerçek export yok)


class PipelineResult(BaseModel):
    """Orchestrator'in döndürdüğü tek nesne.

    Hangi aşamaya kadar gidildiğini ve REVIEW GATE'in durdurup
    durdurmadığını taşır (`stopped_at_stage`).
    """

    session_id: str
    status: PipelineStatus

    preprocessed_audio: Optional[PreprocessedAudio] = None
    transcript: Optional[Transcript] = None
    diarization: Optional[SpeakerSegments] = None
    speaker_labelled_transcript: Optional[SpeakerLabelledTranscript] = None
    role_assignment: Optional[RoleAssignmentResult] = None
    role_labelled_transcript: Optional[RoleLabelledTranscript] = None
    clinical_facts: Optional[ClinicalFactsBundle] = None
    clinical_note: Optional[ClinicalNoteDraft] = None
    procedures: list[ProcedureObject] = Field(default_factory=list)
    code_suggestions: list[CodeSuggestionBundle] = Field(default_factory=list)
    review_decision: Optional[DentistReviewDecision] = None
    export_result: Optional[ExportResult] = None

    stopped_at_stage: Optional[str] = None
