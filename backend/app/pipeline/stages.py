"""
Pipeline aşamaları.

V1'de bu modüldeki fonksiyonların ÇOĞU hâlâ STUB'tır (gerçek ASR/LLM/DB
çağrısı yapmaz) — ama `assign_roles`, `extract_clinical_facts` ve
`generate_clinical_note` artık İSTİSNA: gerçek bir LLM çağrısı yapar
(vendor TBD, `LLMProvider` arabirimi arkasında — CLAUDE.md §6/§10).
Diğer fonksiyonlar doğru TİPTE girdi alır, doğru TİPTE çıktı üretir; içerik
üretimi yoktur ya da bilinçli olarak en güvenli/en belirsiz değeri döner
(CLAUDE.md §4.1 — "belirsizse tahmin etme" kuralı stub veriye de uygulanır).

Orchestration mantığı (özellikle REVIEW GATE) burada DEĞİL — orchestrator.py
'de gerçek çalışır. Bu dosya sadece "her aşama ne üretir" sorusuna cevap
verir.

Somut implementasyon sırası (ilerideki işler, bu görevin kapsamı dışı):
- preprocess_audio:          gerçek normalizasyon / format dönüşümü
- transcribe/diarize/align:  AudioProcessingProvider somut adapter'ı (providers/)
- assign_roles:               BAĞLANDI — prompts/role_assignment.md + LLMProvider
- extract_clinical_facts:     BAĞLANDI — prompts/clinical_facts_extraction.md + LLMProvider
- generate_clinical_note:     BAĞLANDI — prompts/clinical_note_generation.md + LLMProvider
- extract_procedures:         BAĞLANDI — fact JSON'undan deterministik çıkarım
- match_codes_and_checklist:  BAĞLANDI — deterministik fixture DB + opsiyonel LLM açıklama katmanı
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from app.pipeline.types import (
    AudioRef,
    PreprocessedAudio,
    SpeakerLabelledTranscript,
    RoleAssignmentResult,
    RoleLabelledTranscript,
    RoleLabelledUtterance,
    SpeakerRoleAssignment,
    RoleStatus,
    DentistRole,
    ClinicalFact,
    ClinicalFactsBundle,
    ClinicalNoteDraft,
    DentalCondition,
    FactCategory,
    NoteSentence,
    ProcedureObject,
    ProcedureStatus,
    SurfaceCount,
    ToothSurface,
    ToothPerioSummary,
    PerioMeasurement,
    PerioSite,
    ToothType,
    Dentition,
    TreatmentKind,
    CanalCount,
    CodeSuggestionBundle,
    derive_fdi_classification,
    is_valid_fdi_number,
)
from app.prompts.loader import load_system_prompt
from app.providers.audio_processing import AudioProcessingProvider
from app.providers.llm import LLMProvider
from app.tdb.matching import match_codes_and_checklist as _tdb_match_codes_and_checklist

logger = logging.getLogger(__name__)

ROLE_ASSIGNMENT_PROMPT_FILE = "role_assignment.md"
CLINICAL_FACTS_PROMPT_FILE = "clinical_facts_extraction.md"
CLINICAL_NOTE_PROMPT_FILE = "clinical_note_generation.md"
DENTAL_CHART_PROMPT_FILE = "dental_chart_extraction.md"
PERIO_TOOTH_SUMMARY_PROMPT_FILE = "perio_tooth_summary_extraction.md"
PERIO_MULTI_TOOTH_PROMPT_FILE = "perio_multi_tooth_extraction.md"

PERIO_TOOTH_SUMMARY_RESPONSE_SCHEMA = {
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

PERIO_SITE_RESPONSE_SCHEMA = {
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

# Fact kategorisi → ClinicalNoteDraft bölümü. 1:1 eşleşme; FactCategory'de
# bölümsüz kategori yoktur, ClinicalNoteDraft'ta kategorisiz bölüm yoktur.
_CATEGORY_TO_NOTE_SECTION: dict[FactCategory, str] = {
    FactCategory.PATIENT_COMPLAINT: "patient_complaint",
    FactCategory.HISTORY: "history",
    FactCategory.CLINICAL_FINDINGS: "clinical_findings",
    FactCategory.ASSESSMENT: "assessment",
    FactCategory.TREATMENT_PLAN: "treatment_plan",
    FactCategory.PROCEDURES: "procedures_note",
}

# CLAUDE.md §4.2: "Hasta lafı klinik bulgu olamaz." Bu kategoriler sadece
# hekim tarafından doğrulanmış (source_role=dentist) fact'lerden gelebilir.
# PROCEDURES dahil: hasta "yapıldı" dese de bu tek başına işlem kaydı sayılmaz.
_DENTIST_ONLY_CATEGORIES = {
    FactCategory.CLINICAL_FINDINGS,
    FactCategory.ASSESSMENT,
    FactCategory.TREATMENT_PLAN,
    FactCategory.PROCEDURES,
}

# Dentist-only kategori, hasta kaynaklıysa hangi "serbest" kategoriye düşer.
# CLINICAL_FINDINGS/ASSESSMENT/TREATMENT_PLAN → patient_complaint
#   (CLAUDE.md §4.2 örneği: "hasta endişe belirtti").
# PROCEDURES → history: hastanın geçmişte/şu an bir işlem yapıldığına dair
#   iddiası bulgu/işlem kaydı değil, anamnez/geçmiş işlem ANLATISIdır.
_PATIENT_FALLBACK_CATEGORY: dict[FactCategory, FactCategory] = {
    FactCategory.CLINICAL_FINDINGS: FactCategory.PATIENT_COMPLAINT,
    FactCategory.ASSESSMENT: FactCategory.PATIENT_COMPLAINT,
    FactCategory.TREATMENT_PLAN: FactCategory.PATIENT_COMPLAINT,
    FactCategory.PROCEDURES: FactCategory.HISTORY,
}


class SourceRoleInvariantViolation(RuntimeError):
    """REVIEW GATE sızıntısı: `source_role=unknown` olan bir fact bu noktaya
    kadar ulaştı.

    Doğru çalışmada bu HİÇ oluşmamalı: REVIEW GATE (orchestrator.py,
    `_review_gate_blocks`) herhangi bir konuşmacı `unknown`/`unresolved` ise
    pipeline'ı facts extraction'a gelmeden zaten durdurur. Bu hatanın
    fırlatılması, gate'in bir şekilde atlandığını/bypass edildiğini gösterir
    — bu yüzden sessizce yutulmaz, görünür şekilde patlar.

    KVKK (CLAUDE.md §5): mesaj ve `session_id`/`speaker_id`/`category`
    dışında HİÇBİR veri taşımaz — özellikle HAM `source_quote` asla buraya
    (ve dolayısıyla loga/traceback'e) sızmaz.
    """

    def __init__(self, session_id: str, speaker_id: str, category: FactCategory) -> None:
        self.session_id = session_id
        self.speaker_id = speaker_id
        self.category = category
        super().__init__(
            f"Fact source_role=unknown (session_id={session_id!r}, "
            f"speaker={speaker_id!r}, category={category.value!r}) — "
            "REVIEW GATE bu durumu durdurmalıydı; sessizce yutulmuyor."
        )


def _enforce_source_role_invariant(facts: ClinicalFactsBundle) -> ClinicalFactsBundle:
    """CLAUDE.md §4.2 invariant'ı — fact→note VE fact→procedure adımlarının
    HER İKİSİNDE de bağımsız olarak uygulanır (defense in depth). Upstream
    extraction adımı bu kuralı zaten uygulamış olsa da olmasa da, klinik
    bulgu/tanı/tedavi planı/işlem kaydı asla `dentist` olmayan bir
    `source_role`'den geçip not'a veya procedure'e sızmaz.

    Guard (ilk adım): herhangi bir fact'in `source_role`'ü `UNKNOWN` ise bu
    bir REVIEW GATE sızıntısıdır — loglanır ve `SourceRoleInvariantViolation`
    fırlatılır (bkz. sınıf docstring'i). Bu kontrol diğer her şeyden ÖNCE
    yapılır; sızıntı varsa yeniden kategorize/uncertain_items'a düşürme gibi
    "kurtarma" davranışlarına asla geçilmez.

    `clinical_findings` / `assessment` / `treatment_plan` / `procedures`
    kategorisindeki bir fact'in `source_role`'ü `DENTIST` DEĞİLSE:
      - `source_role == PATIENT` ise → `_PATIENT_FALLBACK_CATEGORY`'deki
        karşılığına yeniden kategorize edilir (SİLİNMEZ).
      - aksi halde (`assistant_or_other`) → `uncertain_items`'a metin olarak
        eklenir, yapılandırılmış fact listesinden çıkarılır.
    """
    for fact in facts.facts:
        if fact.source_role == DentistRole.UNKNOWN:
            # KVKK (CLAUDE.md §5): ham source_quote ASLA loglanmaz — yalnızca
            # session_id + speaker_id + kategori.
            logger.error(
                "source_role_invariant_violation: session_id=%s speaker=%s "
                "category=%s — REVIEW GATE bu durumu durdurmalıydı.",
                facts.session_id,
                fact.source_speaker,
                fact.category.value,
            )
            raise SourceRoleInvariantViolation(
                session_id=facts.session_id,
                speaker_id=fact.source_speaker,
                category=fact.category,
            )

    safe_facts: list[ClinicalFact] = []
    uncertain_items = list(facts.uncertain_items)

    for fact in facts.facts:
        if fact.category in _DENTIST_ONLY_CATEGORIES and fact.source_role != DentistRole.DENTIST:
            if fact.source_role == DentistRole.PATIENT:
                fallback_category = _PATIENT_FALLBACK_CATEGORY[fact.category]
                safe_facts.append(fact.model_copy(update={"category": fallback_category}))
            else:
                uncertain_items.append(
                    f"[{fact.source_role.value}/{fact.source_speaker}] {fact.source_quote}"
                )
            continue
        safe_facts.append(fact)

    return ClinicalFactsBundle(
        session_id=facts.session_id,
        facts=safe_facts,
        uncertain_items=uncertain_items,
    )


def preprocess_audio(audio: AudioRef) -> PreprocessedAudio:
    """STUB: gerçek normalizasyon/format dönüşümü yok; referansı taşır."""
    return PreprocessedAudio(
        session_id=audio.session_id,
        storage_uri=audio.storage_uri,
        normalized=True,
        duration_sec=audio.duration_sec,
    )


def transcribe_and_diarize_and_align(
    preprocessed: PreprocessedAudio, provider: AudioProcessingProvider
) -> SpeakerLabelledTranscript:
    """ASR + diarization + alignment.

    Somut vendor henüz yok (CLAUDE.md §10 TBD); bu fonksiyon vendor-agnostic
    `AudioProcessingProvider` arabirimine delege eder. `provider` somut bir
    implementasyon olmadan çağrılırsa (örn. test/placeholder adapter),
    `transcribe`/`diarize`/`align` kendi NotImplementedError'ını fırlatır —
    burada sahte veri ÜRETİLMEZ.
    """
    audio_ref = AudioRef(session_id=preprocessed.session_id, storage_uri=preprocessed.storage_uri)
    transcript = provider.transcribe(audio_ref)
    diarization = provider.diarize(audio_ref)
    return provider.align(transcript, diarization)


def assign_roles(transcript: SpeakerLabelledTranscript, llm: LLMProvider) -> RoleAssignmentResult:
    """role_assignment LLM aşaması (prompts/role_assignment.md) — STUB DEĞİL.

    Gerçek bir LLM çağrısı yapılır (somut vendor TBD, CLAUDE.md §6/§10 —
    `LLMProvider` arabirimi arkasında). Ama kod tarafı LLM çıktısına KÖRÜ
    KÖRÜNE güvenmez; prompt dosyasındaki "Doğrulama notları" bölümünün TÜMÜ
    burada BAĞIMSIZ olarak (defense in depth) uygulanır:

      1. LLM çıktısı parse edilemezse / beklenen JSON sözleşmesine uymazsa
         (örn. bir speaker_id eksik/fazla) → fail-safe: her konuşmacı
         `unknown`/`unresolved`, `manual_review_required=True`. Asla sahte/
         varsayılan bir ROL üretilmez — sadece "bilmiyorum" işaretlenir.
      2. `utterance_count`, LLM'in raporuna güvenilmeden TRANSKRİPTTEN
         yeniden hesaplanır (CLAUDE.md §4.9'daki FDI doğrulama ruhu: kritik
         sayısal alanlar daima kaynaktan doğrulanır, modele güvenilmez).
      3. Gerçek `utterance_count <= 1` ise `status=clear` asla kabul
         edilmez; `review_needed`'e düşürülür (CLAUDE.md §4.8) — LLM "clear"
         dese de.
      4. Herhangi bir kayıt `unknown`/`unresolved`/`review_needed` ise
         `manual_review_required` ZORLA `True` yapılır — LLM bunu `False`
         dese de (prompt'la çelişki bırakılmaz; kod fail-safe tarafı seçer).

    Hiçbir koşulda bu fonksiyon REVIEW GATE'i atlatacak şekilde "iyimser"
    bir sonuç üretmez; emin değilse her zaman daha güvenli (daha fazla
    review/unresolved) tarafa düşer.
    """
    true_utterance_counts: dict[str, int] = {}
    for u in transcript.utterances:
        true_utterance_counts[u.speaker_id] = true_utterance_counts.get(u.speaker_id, 0) + 1
    speaker_ids = sorted(true_utterance_counts.keys())

    if not speaker_ids:
        # Konuşmacı yok — değerlendirilecek bir şey yok; güvenli taraf: dur.
        return RoleAssignmentResult(
            session_id=transcript.session_id, assignments=[], manual_review_required=True
        )

    system_prompt = load_system_prompt(ROLE_ASSIGNMENT_PROMPT_FILE)
    user_input = _build_role_assignment_user_input(transcript)

    try:
        raw_output = llm.complete(system_prompt, user_input)
        data = json.loads(raw_output)
        # Sözleşme üst seviye anahtarı "assignments"tır (prompts/role_assignment.md).
        # Savunma: model yanlışlıkla "speakers" ile dönerse de kabul et — ama
        # ikisi de yoksa KeyError fırlar ve aşağıdaki except fail-safe'e düşürür
        # (tamamen geçersiz çıktı yine fail-safe'e gider, burada genişletilmiyor).
        assignments_field = data["assignments"] if "assignments" in data else data["speakers"]
        llm_assignments_by_speaker = {str(item["speaker_id"]): item for item in assignments_field}
        llm_manual_review_required = bool(data["manual_review_required"])
    except Exception:
        # KVKK (CLAUDE.md §5): ham LLM çıktısı/transkript metni loga YAZILMAZ
        # — yalnızca session_id.
        logger.error(
            "role_assignment_llm_output_unparseable: session_id=%s — fail-safe'e düşülüyor.",
            transcript.session_id,
        )
        return _fail_safe_role_assignment(transcript.session_id, speaker_ids, true_utterance_counts)

    # Sözleşme: assignments transcript'teki speaker_id kümesiyle BİREBİR eşleşmeli
    # (CLAUDE.md §4.8 — hiçbir konuşmacı atlanmaz/icat edilmez).
    if set(llm_assignments_by_speaker.keys()) != set(speaker_ids):
        logger.error(
            "role_assignment_speaker_set_mismatch: session_id=%s expected=%s got=%s — "
            "fail-safe'e düşülüyor.",
            transcript.session_id,
            speaker_ids,
            sorted(llm_assignments_by_speaker.keys()),
        )
        return _fail_safe_role_assignment(transcript.session_id, speaker_ids, true_utterance_counts)

    final_assignments: list[SpeakerRoleAssignment] = []
    for sid in speaker_ids:
        item = llm_assignments_by_speaker[sid]
        try:
            role = DentistRole(item["role"])
            status = RoleStatus(item["status"])
            reason = item.get("reason")
        except Exception:
            logger.error(
                "role_assignment_item_invalid: session_id=%s speaker=%s — fail-safe'e düşülüyor.",
                transcript.session_id,
                sid,
            )
            return _fail_safe_role_assignment(transcript.session_id, speaker_ids, true_utterance_counts)

        real_count = true_utterance_counts[sid]
        if real_count <= 1 and status == RoleStatus.CLEAR:
            status = RoleStatus.REVIEW_NEEDED
            reason = (
                f"{reason} "
                if reason
                else ""
            ) + "[kod: tek-ifadeli konuşmacı clear olamaz (CLAUDE.md §4.8), review_needed'e düşürüldü]"

        final_assignments.append(
            SpeakerRoleAssignment(
                speaker_id=sid,
                role=role,
                status=status,
                utterance_count=real_count,  # LLM'in raporuna değil, transkriptten hesaplanan gerçek sayı
                reason=reason,
            )
        )

    needs_review = any(
        a.status in (RoleStatus.UNRESOLVED, RoleStatus.REVIEW_NEEDED) or a.role == DentistRole.UNKNOWN
        for a in final_assignments
    )
    manual_review_required = llm_manual_review_required or needs_review

    return RoleAssignmentResult(
        session_id=transcript.session_id,
        assignments=final_assignments,
        manual_review_required=manual_review_required,
    )


def _build_role_assignment_user_input(transcript: SpeakerLabelledTranscript) -> str:
    """Prompt dosyasının 'Input format' bölümüyle hizalı kullanıcı girdisi."""
    utterances_json = json.dumps(
        [{"speaker_id": u.speaker_id, "text": u.text} for u in transcript.utterances],
        ensure_ascii=False,
    )
    return f"Transcript (speaker-labelled, neutral IDs):\n{utterances_json}"


def _fail_safe_role_assignment(
    session_id: str, speaker_ids: list[str], utterance_counts: dict[str, int]
) -> RoleAssignmentResult:
    """LLM çıktısı parse edilemediğinde / sözleşmeyi bozduğunda dönülen
    güvenli varsayılan: her konuşmacı `unknown`/`unresolved`, gate durur.

    Sahte/varsayılan bir ROL asla üretilmez — sadece "bilmiyorum" işaretlenir
    (CLAUDE.md §4.1: belirsizse tahmin etme; prompt dosyası "Doğrulama
    notları": "parse hatası = manual_review_required, sahte atama değil").
    """
    assignments = [
        SpeakerRoleAssignment(
            speaker_id=sid,
            role=DentistRole.UNKNOWN,
            status=RoleStatus.UNRESOLVED,
            utterance_count=utterance_counts.get(sid, 0),
            reason="LLM çıktısı parse edilemedi veya beklenen sözleşmeyi bozdu (fail-safe).",
        )
        for sid in speaker_ids
    ]
    return RoleAssignmentResult(
        session_id=session_id, assignments=assignments, manual_review_required=True
    )


def apply_dentist_role_correction(
    transcript: SpeakerLabelledTranscript, corrected: RoleAssignmentResult
) -> RoleLabelledTranscript:
    """Hekimin REVIEW GATE'te verdiği rol düzeltmesini transkripte uygular.

    Bu fonksiyon her zaman REVIEW GATE geçildikten SONRA çağrılır
    (orchestrator.py); `corrected` parametresi artık unresolved/unknown
    içermediği (ya da bilerek öyle bırakıldığı — bu durumda gate yine
    durdurur) varsayılan bir atamadır.
    """
    role_by_speaker = {a.speaker_id: a.role for a in corrected.assignments}
    utterances = [
        RoleLabelledUtterance(
            speaker_id=u.speaker_id,
            role=role_by_speaker[u.speaker_id],
            text=u.text,
            start_sec=u.start_sec,
            end_sec=u.end_sec,
        )
        for u in transcript.utterances
        if u.speaker_id in role_by_speaker
    ]
    return RoleLabelledTranscript(session_id=transcript.session_id, utterances=utterances)


def extract_clinical_facts(transcript: RoleLabelledTranscript, llm: LLMProvider) -> ClinicalFactsBundle:
    """clinical_facts_extraction LLM aşaması — STUB DEĞİL.

    Gerçek bir LLM çağrısı yapılır, ama çıktı sadece beklenen JSON sözleşmesine
    uyarsa kabul edilir. Parse/sözleşme/provenance hatasında fail-safe:
    boş fact listesi + hekim inceleme uyarısı. Asla kaynaksız fact üretilmez
    (CLAUDE.md §4.1, §4.6).
    """
    system_prompt = load_system_prompt(CLINICAL_FACTS_PROMPT_FILE)
    user_input = _build_clinical_facts_user_input(transcript)

    try:
        raw_output = llm.complete(system_prompt, user_input)
        data = _normalize_clinical_facts_payload(_loads_llm_json_object(raw_output))
        facts = ClinicalFactsBundle.model_validate(
            {
                "session_id": transcript.session_id,
                "facts": data["facts"],
                "uncertain_items": data["uncertain_items"],
            }
        )
        _validate_fact_source_quotes(transcript, facts)
        facts = _normalize_validated_clinical_facts(transcript, facts)
    except Exception:
        # KVKK (CLAUDE.md §5): ham LLM çıktısı/transkript metni loga YAZILMAZ
        # — yalnızca session_id.
        logger.error(
            "clinical_facts_llm_output_unparseable: session_id=%s — fail-safe'e düşülüyor.",
            transcript.session_id,
        )
        return _fallback_clinical_facts_from_transcript(transcript)

    return _enforce_source_role_invariant(facts)


def _build_clinical_facts_user_input(transcript: RoleLabelledTranscript) -> str:
    """Prompt dosyasının 'Input format' bölümüyle hizalı kullanıcı girdisi."""
    utterances_json = json.dumps(
        [
            {"speaker_id": u.speaker_id, "role": u.role.value, "text": u.text}
            for u in transcript.utterances
        ],
        ensure_ascii=False,
    )
    return f"Transcript (role-labelled):\n{utterances_json}"


def _normalize_clinical_facts_payload(data: object) -> dict:
    """LLM'in küçük alan adı sapmalarını kabul et; klinik içerik uydurma.

    Sözleşme top-level anahtarı `facts`tır. Savunma olarak eski/olası
    `clinical_facts` ve `extracted_facts` alias'ları da kabul edilir.
    """
    if not isinstance(data, dict):
        raise ValueError("clinical facts payload dict değil")

    facts_field = _first_present(data, ("facts", "clinical_facts", "extracted_facts"))
    uncertain_items = _first_present(
        data,
        ("uncertain_items", "uncertainties", "unclear_items", "review_items"),
        default=[],
    )

    if not isinstance(facts_field, list) or not isinstance(uncertain_items, list):
        raise ValueError("clinical facts payload alan tipleri geçersiz")

    normalized_facts = []
    for item in facts_field:
        if not isinstance(item, dict):
            raise ValueError("clinical fact item dict değil")
        source_quote = _first_present(item, ("source_quote", "quote", "evidence_quote"))
        normalized_facts.append(
            {
                "category": _first_present(item, ("category", "fact_category", "type")),
                "text": _first_present(item, ("text", "fact_text", "summary"), default=source_quote),
                "source_quote": source_quote,
                "source_role": _first_present(item, ("source_role", "role")),
                "source_speaker": _first_present(item, ("source_speaker", "speaker_id", "speaker")),
                "tooth_number_fdi": _first_present(item, ("tooth_number_fdi", "fdi", "tooth_number"), default=None),
                "status": _first_present(item, ("status", "procedure_status"), default=None),
                "is_uncertain": bool(_first_present(item, ("is_uncertain", "uncertain"), default=False)),
            }
        )

    return {"facts": normalized_facts, "uncertain_items": [str(i) for i in uncertain_items]}


def _loads_llm_json_object(raw_output: str) -> object:
    """LLM JSON modunda bile bazen geçerli objeden sonra fence/brace artığı
    bırakabiliyor. İlk geçerli JSON nesnesini al; anlamlı ekstra metin varsa
    parse hatası say.
    """
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


def _validate_fact_source_quotes(
    transcript: RoleLabelledTranscript, facts: ClinicalFactsBundle
) -> None:
    """Her source_quote transkriptte birebir geçmeli ve speaker/role eşleşmeli."""
    utterance_by_speaker: dict[str, list[RoleLabelledUtterance]] = {}
    for utterance in transcript.utterances:
        utterance_by_speaker.setdefault(utterance.speaker_id, []).append(utterance)

    for fact in facts.facts:
        matching_utterances = [
            u
            for u in utterance_by_speaker.get(fact.source_speaker, [])
            if fact.source_quote and fact.source_quote in u.text
        ]
        if not matching_utterances:
            raise ValueError("source_quote transkriptte birebir bulunamadı")
        if not any(u.role == fact.source_role for u in matching_utterances):
            raise ValueError("source_role transcript role ile eşleşmedi")
        if fact.tooth_number_fdi is not None and not _is_valid_fdi(fact.tooth_number_fdi):
            raise ValueError("geçersiz FDI")


def _normalize_validated_clinical_facts(
    transcript: RoleLabelledTranscript, facts: ClinicalFactsBundle
) -> ClinicalFactsBundle:
    """Klinik içerik üretmeden sözleşme normalizasyonu yap.

    - `status` yalnızca `procedures` fact'lerinde anlamlıdır.
    - Hasta/asistan kaynaklı FDI, aynı utterance'ta açık sayı yoksa taşınmaz;
      bu, hastanın "bu diş" sözünden hekim cümlesindeki numarayı modele
      taşıtmamaya yarayan güvenli bir guard'dır. Hekim kaynaklı FDI bağlamı
      taşınabilir, ama mırıltılı/okunmayan numara temizlenir.
    """
    utterances_by_speaker: dict[str, list[RoleLabelledUtterance]] = {}
    for utterance in transcript.utterances:
        utterances_by_speaker.setdefault(utterance.speaker_id, []).append(utterance)

    normalized: list[ClinicalFact] = []
    for fact in facts.facts:
        updates = {}
        source_utterance = next(
            (
                u
                for u in utterances_by_speaker.get(fact.source_speaker, [])
                if fact.source_quote in u.text
            ),
            None,
        )
        source_text_lower = source_utterance.text.lower() if source_utterance else ""

        if fact.category != FactCategory.PROCEDURES and fact.status is not None:
            updates["status"] = None
        if (
            fact.category == FactCategory.CLINICAL_FINDINGS
            and ("tam okunmuyor" in source_text_lower or "mi, tam" in source_text_lower)
            and not fact.is_uncertain
        ):
            updates["is_uncertain"] = True
        if fact.tooth_number_fdi is not None:
            if source_utterance is None:
                updates["tooth_number_fdi"] = None
            else:
                if "tam okunmuyor" in source_text_lower or "mi, tam" in source_text_lower:
                    updates["tooth_number_fdi"] = None
                elif fact.source_role != DentistRole.DENTIST and str(fact.tooth_number_fdi) not in source_utterance.text:
                    updates["tooth_number_fdi"] = None
        normalized.append(fact.model_copy(update=updates) if updates else fact)

    uncertain_items = list(facts.uncertain_items)
    transcript_text_lower = "\n".join(u.text for u in transcript.utterances).lower()
    if "tam okunmuyor" in transcript_text_lower and not any(
        "diş numarası" in item.lower() for item in uncertain_items
    ):
        uncertain_items.append("Diş numarası net değil: transkriptte numaranın tam okunmadığı belirtilmiş.")

    return ClinicalFactsBundle(
        session_id=facts.session_id,
        facts=normalized,
        uncertain_items=uncertain_items,
    )


def _is_valid_fdi(tooth_number: int) -> bool:
    return is_valid_fdi_number(tooth_number)


def _fail_safe_clinical_facts(session_id: str) -> ClinicalFactsBundle:
    return ClinicalFactsBundle(
        session_id=session_id,
        facts=[],
        uncertain_items=[
            "Clinical facts extraction çıktısı parse edilemedi veya provenance doğrulamasını geçemedi; hekim incelemesi gerekir."
        ],
    )


def _fallback_clinical_facts_from_transcript(transcript: RoleLabelledTranscript) -> ClinicalFactsBundle:
    """Parse fail durumunda güvenli, kanıtlı minimum fact çıkarımı.

    Bu fallback klinik içerik tahmini yapmaz: yalnızca tek utterance içinde açıkça
    görünen hasta şikayeti veya hekim kaynaklı FDI/procedure ifadelerini taşır.
    Her `source_quote` utterance metninin birebir kendisidir; böylece provenance
    bozulmaz. Dentist-only kategoriler için hasta/asistan cümlesi kullanılmaz.
    """
    facts: list[ClinicalFact] = []
    for utterance in transcript.utterances:
        text = utterance.text.strip()
        if not text:
            continue
        normalized = _normalize_lookup_text(text)

        if utterance.role == DentistRole.PATIENT and _looks_like_patient_complaint(normalized):
            facts.append(
                ClinicalFact(
                    category=FactCategory.PATIENT_COMPLAINT,
                    text=text,
                    source_quote=text,
                    source_role=DentistRole.PATIENT,
                    source_speaker=utterance.speaker_id,
                    tooth_number_fdi=None,
                    status=None,
                    is_uncertain=False,
                )
            )
            continue

        if utterance.role != DentistRole.DENTIST:
            continue

        tooth_number_fdi = _extract_explicit_fdi_from_text(normalized)
        has_procedure = _fallback_detects_procedure(normalized)
        has_finding = _fallback_detects_finding(normalized)
        has_assessment = _fallback_detects_assessment(normalized)
        has_plan = _fallback_detects_plan(normalized)

        if has_finding:
            facts.append(
                ClinicalFact(
                    category=FactCategory.CLINICAL_FINDINGS,
                    text=text,
                    source_quote=text,
                    source_role=DentistRole.DENTIST,
                    source_speaker=utterance.speaker_id,
                    tooth_number_fdi=tooth_number_fdi,
                    status=None,
                    is_uncertain=_has_uncertain_language(normalized),
                )
            )
        if has_assessment:
            facts.append(
                ClinicalFact(
                    category=FactCategory.ASSESSMENT,
                    text=text,
                    source_quote=text,
                    source_role=DentistRole.DENTIST,
                    source_speaker=utterance.speaker_id,
                    tooth_number_fdi=tooth_number_fdi,
                    status=None,
                    is_uncertain=True,
                )
            )
        if has_plan:
            facts.append(
                ClinicalFact(
                    category=FactCategory.TREATMENT_PLAN,
                    text=text,
                    source_quote=text,
                    source_role=DentistRole.DENTIST,
                    source_speaker=utterance.speaker_id,
                    tooth_number_fdi=tooth_number_fdi,
                    status=None,
                    is_uncertain=_has_uncertain_language(normalized),
                )
            )
        if has_procedure and not _is_negated_procedure_text(normalized):
            facts.append(
                ClinicalFact(
                    category=FactCategory.PROCEDURES,
                    text=text,
                    source_quote=text,
                    source_role=DentistRole.DENTIST,
                    source_speaker=utterance.speaker_id,
                    tooth_number_fdi=tooth_number_fdi,
                    status=_fallback_procedure_status(normalized),
                    is_uncertain=_has_uncertain_language(normalized),
                )
            )

    return _enforce_source_role_invariant(
        ClinicalFactsBundle(
            session_id=transcript.session_id,
            facts=facts,
            uncertain_items=[
                "Clinical facts extraction çıktısı parse edilemedi; güvenli minimum fallback ile yalnızca açık kaynaklı ifadeler taşındı."
            ],
        )
    )


def _looks_like_patient_complaint(text: str) -> bool:
    return _has_any(text, ("ağrı", "agri", "hassasiyet", "zonkl", "şikayet", "sikayet", "iltihaplı mı", "iltihapli mi"))


def _fallback_detects_finding(text: str) -> bool:
    return _has_any(text, ("görüyorum", "goruyorum", "var", "röntgen", "rontgen", "perküsyon", "perkusyon", "periapikal", "çürük", "curuk"))


def _fallback_detects_assessment(text: str) -> bool:
    return _has_any(text, ("gerekebilir", "şüpheli", "supheli", "değerlendireceğiz", "degerlendirecegiz", "kesin olarak söylemek zor", "olabilir"))


def _fallback_detects_plan(text: str) -> bool:
    return _has_any(text, ("plan", "yapalım", "yapalim", "başlarız", "baslariz", "ilerleyeceğiz", "ilerleyecegiz", "deneyelim"))


def _fallback_detects_procedure(text: str) -> bool:
    return _has_any(text, ("kanal tedavisi", "endodontik", "dolgu", "restorasyon", "kompozit", "çekim", "cekim"))


def _has_uncertain_language(text: str) -> bool:
    return _has_any(text, ("gerekebilir", "şüpheli", "supheli", "olabilir", "değerlendireceğiz", "degerlendirecegiz", "kesin olarak söylemek zor"))


def _fallback_procedure_status(text: str) -> ProcedureStatus:
    if _has_any(text, ("yapıldı", "yapildi", "tamamlandı", "tamamlandi")):
        return ProcedureStatus.PERFORMED
    if _has_any(text, ("planlandı", "planlandi", "planlayalım", "planlayalim", "yapılacak", "yapilacak", "başlarız", "baslariz", "yapalım", "yapalim")):
        return ProcedureStatus.PLANNED
    if _has_uncertain_language(text):
        return ProcedureStatus.DISCUSSED
    return ProcedureStatus.UNCLEAR


def _extract_explicit_fdi_from_text(text: str) -> Optional[int]:
    digit_match = re.search(r"\b([1-8][1-8])\b", text)
    if digit_match:
        candidate = int(digit_match.group(1))
        return candidate if _is_valid_fdi(candidate) else None

    phrase_map: tuple[tuple[str, int], ...] = (
        ("sağ alt altı", 46),
        ("sag alt alti", 46),
        ("sağ alt 6", 46),
        ("sag alt 6", 46),
        ("sol alt altı", 36),
        ("sol alt alti", 36),
        ("sağ üst altı", 16),
        ("sag ust alti", 16),
        ("sağ ust alti", 16),
        ("sol üst altı", 26),
        ("sol ust alti", 26),
        ("kırk altı", 46),
        ("kirk alti", 46),
        ("kırk dört", 44),
        ("kirk dort", 44),
        ("otuz altı", 36),
        ("otuz alti", 36),
        ("yirmi altı", 26),
        ("yirmi alti", 26),
        ("on altı", 16),
        ("on alti", 16),
    )
    for phrase, tooth_number in phrase_map:
        if phrase in text:
            return tooth_number
    return None


def generate_clinical_note(facts: ClinicalFactsBundle, llm: LLMProvider) -> ClinicalNoteDraft:
    """clinical_note_generation LLM aşaması — STUB DEĞİL.

    Kontrat (CLAUDE.md aşama 2→3): yalnızca `facts`'ten üretir, yeni bilgi
    eklemez, PARAPHRASE ETMEZ — her `NoteSentence.text` ilgili fact'in
    `text`'i, `source_quote`/`source_role` o fact'ten DEĞİŞMEDEN taşınır.

    LLM çıktısı bu kontratı bozarsa sessizce kabul edilmez; güvenli
    deterministik fact→note taşımasına düşülür. Bu fallback yeni bilgi
    üretmez, sadece zaten güvenli sayılmış fact'leri doğru bölüme taşır.

    Invariant (CLAUDE.md §4.2) burada BAĞIMSIZ olarak da uygulanır:
    `_enforce_source_role_invariant` upstream extraction'a güvenmeden,
    dentist olmayan source_role'den gelen clinical_findings/assessment/
    treatment_plan fact'lerini not'a bulgu olarak girmeden önce yeniden
    kategorize eder/eler.
    """
    safe_facts = _enforce_source_role_invariant(facts)

    system_prompt = load_system_prompt(CLINICAL_NOTE_PROMPT_FILE)
    user_input = _build_clinical_note_user_input(safe_facts)

    try:
        raw_output = llm.complete(system_prompt, user_input)
        note = _normalize_clinical_note_payload(
            safe_facts.session_id,
            _loads_llm_json_object(raw_output),
        )
        _validate_note_against_facts(safe_facts, note)
        return _attach_note_provenance_metadata(safe_facts, note)
    except Exception:
        # KVKK (CLAUDE.md §5): ham LLM çıktısı/fact metni loga YAZILMAZ
        # — yalnızca session_id.
        logger.error(
            "clinical_note_llm_output_invalid: session_id=%s — deterministik fact->note fallback kullanılıyor.",
            safe_facts.session_id,
        )
        return _deterministic_clinical_note_from_facts(safe_facts)


def _deterministic_clinical_note_from_facts(facts: ClinicalFactsBundle) -> ClinicalNoteDraft:
    """Güvenli fallback: her fact'i kategori eşleşmesine göre not bölümüne taşır."""
    sections: dict[str, list[NoteSentence]] = {section: [] for section in _CATEGORY_TO_NOTE_SECTION.values()}
    for idx, fact in enumerate(facts.facts):
        section = _CATEGORY_TO_NOTE_SECTION.get(fact.category)
        if section is None:
            continue
        sections[section].append(
            NoteSentence(
                sentence_id=f"s{idx}",
                text=fact.text,
                source_role=fact.source_role,
                source_quote=fact.source_quote,
                source_speaker=fact.source_speaker,
                source_role_confidence=fact.source_role_confidence,
            )
        )

    return ClinicalNoteDraft(
        session_id=facts.session_id,
        uncertain_items=list(facts.uncertain_items),
        **sections,
    )


def _attach_note_provenance_metadata(
    facts: ClinicalFactsBundle, note: ClinicalNoteDraft
) -> ClinicalNoteDraft:
    metadata_by_key = {
        (fact.text, fact.source_role, fact.source_quote): (
            fact.source_speaker,
            fact.source_role_confidence,
        )
        for fact in facts.facts
    }
    updates = {}
    for section in _CATEGORY_TO_NOTE_SECTION.values():
        sentences = []
        for sentence in getattr(note, section):
            source_speaker, source_role_confidence = metadata_by_key.get(
                (sentence.text, sentence.source_role, sentence.source_quote),
                (sentence.source_speaker, sentence.source_role_confidence),
            )
            sentences.append(
                sentence.model_copy(
                    update={
                        "source_speaker": source_speaker,
                        "source_role_confidence": source_role_confidence,
                    }
                )
            )
        updates[section] = sentences
    return note.model_copy(update=updates)


def _build_clinical_note_user_input(facts: ClinicalFactsBundle) -> str:
    """Prompt dosyasının 'Input format' bölümüyle hizalı kullanıcı girdisi."""
    return "Clinical facts bundle:\n" + facts.model_dump_json(exclude_none=False)


def _normalize_clinical_note_payload(session_id: str, data: object) -> ClinicalNoteDraft:
    if not isinstance(data, dict):
        raise ValueError("clinical note payload dict değil")

    payload = {
        "session_id": session_id,
        "patient_complaint": _first_present(data, ("patient_complaint",), default=[]),
        "history": _first_present(data, ("history",), default=[]),
        "clinical_findings": _first_present(data, ("clinical_findings",), default=[]),
        "assessment": _first_present(data, ("assessment",), default=[]),
        "treatment_plan": _first_present(data, ("treatment_plan",), default=[]),
        "procedures_note": _first_present(data, ("procedures_note", "procedures"), default=[]),
        "uncertain_items": _first_present(data, ("uncertain_items", "uncertainties"), default=[]),
        "is_draft": _first_present(data, ("is_draft",), default=True),
    }
    return ClinicalNoteDraft.model_validate(payload)


def _validate_note_against_facts(facts: ClinicalFactsBundle, note: ClinicalNoteDraft) -> None:
    """Note cümleleri input fact'leri birebir ve doğru section'da taşımalı."""
    if note.session_id != facts.session_id:
        raise ValueError("note session_id facts ile eşleşmedi")
    if not note.is_draft:
        raise ValueError("note is_draft=false olamaz")
    if note.uncertain_items != facts.uncertain_items:
        raise ValueError("uncertain_items birebir taşınmadı")

    expected_by_section: dict[str, list[tuple[str, DentistRole, str]]] = {
        section: [] for section in _CATEGORY_TO_NOTE_SECTION.values()
    }
    for fact in facts.facts:
        section = _CATEGORY_TO_NOTE_SECTION.get(fact.category)
        if section is None:
            continue
        expected_by_section[section].append((fact.text, fact.source_role, fact.source_quote))

    actual_by_section: dict[str, list[tuple[str, DentistRole, str]]] = {
        "patient_complaint": [(s.text, s.source_role, s.source_quote) for s in note.patient_complaint],
        "history": [(s.text, s.source_role, s.source_quote) for s in note.history],
        "clinical_findings": [(s.text, s.source_role, s.source_quote) for s in note.clinical_findings],
        "assessment": [(s.text, s.source_role, s.source_quote) for s in note.assessment],
        "treatment_plan": [(s.text, s.source_role, s.source_quote) for s in note.treatment_plan],
        "procedures_note": [(s.text, s.source_role, s.source_quote) for s in note.procedures_note],
    }

    if actual_by_section != expected_by_section:
        raise ValueError("note cümleleri fact'lerle birebir/doğru bölümde eşleşmedi")


def extract_procedures(facts: ClinicalFactsBundle) -> list[ProcedureObject]:
    """Fact JSON'undan deterministik procedure extraction.

    LLM çağrısı YOK; yalnızca `ClinicalFact(category=procedures)` kayıtları
    kapalı ve küçük bir kural setiyle `ProcedureObject`'e çevrilir. Tanınmayan
    işlem ailesi için obje üretilmez — procedure_family uydurmak sonraki kod
    eşleştirme adımında kapalı DB kuralını zedeler (CLAUDE.md §4.1, §4.5).

    Invariant (CLAUDE.md §4.2) burada da BAĞIMSIZ uygulanır: hasta/asistan
    kaynaklı procedure iddiası işlem objesine dönüşmez.
    """
    safe_facts = _enforce_source_role_invariant(facts)
    procedures: list[ProcedureObject] = []

    for fact in safe_facts.facts:
        if fact.category != FactCategory.PROCEDURES or fact.source_role != DentistRole.DENTIST:
            continue

        procedure_family = _detect_procedure_family(fact)
        if procedure_family is None:
            continue

        tooth_number_fdi = fact.tooth_number_fdi if _is_valid_optional_fdi(fact.tooth_number_fdi) else None
        dentition, tooth_type, tooth_group = derive_fdi_classification(tooth_number_fdi)
        procedures.append(
            ProcedureObject(
                procedure_family=procedure_family,
                tooth_number_fdi=tooth_number_fdi,
                dentition=dentition,
                tooth_type=tooth_type,
                tooth_group=tooth_group,
                surface_count=_detect_surface_count(fact),
                canal_count=_detect_canal_count(fact) if procedure_family == "kanal_tedavisi" else None,
                treatment_kind=_detect_treatment_kind(fact) if procedure_family == "kanal_tedavisi" else None,
                status=fact.status or ProcedureStatus.UNCLEAR,
                source_quotes=[fact.source_quote],
            )
        )

    return procedures


def extract_dental_chart_commands(
    facts: ClinicalFactsBundle, llm: LLMProvider
) -> list[ProcedureObject]:
    """Dental chart NLU enrichment: ProcedureObject + yüzey/kondisyon.

    Mevcut deterministik `extract_procedures` korunur. Bu aşama yalnızca
    hekim kaynaklı procedure fact'lerini `docs/dental-chart-nlu-spec.md`
    kurallarına göre LLM ile zenginleştirir; parse/enum/FDI hatasında
    güvenli tarafta kalır ve mevcut procedure bilgisini bozmaz.
    """
    safe_facts = _enforce_source_role_invariant(facts)
    base_procedures = extract_procedures(safe_facts)
    procedure_facts = [
        fact
        for fact in safe_facts.facts
        if fact.category == FactCategory.PROCEDURES
        and fact.source_role == DentistRole.DENTIST
        and not _is_negated_procedure_text(_procedure_text(fact))
    ]

    system_prompt = load_system_prompt(DENTAL_CHART_PROMPT_FILE)
    enriched: list[ProcedureObject] = []
    for idx, procedure in enumerate(base_procedures):
        fact = procedure_facts[idx] if idx < len(procedure_facts) else None
        if fact is None:
            enriched.append(procedure)
            continue

        try:
            raw_output = llm.complete(system_prompt, _build_dental_chart_user_input(fact))
            items = _normalize_dental_chart_payload(_loads_llm_json_array(raw_output))
        except Exception:
            logger.error(
                "dental_chart_llm_output_unparseable: session_id=%s — mevcut procedure korunuyor.",
                safe_facts.session_id,
            )
            _append_dental_chart_uncertainty(
                facts,
                safe_facts,
                f"Dental chart çıkarımı parse edilemedi: {fact.source_quote}",
            )
            enriched.append(procedure)
            continue

        item = _select_dental_chart_item(items, fact)
        if item is None:
            _append_dental_chart_uncertainty(
                facts,
                safe_facts,
                f"Dental chart çıkarımı belirsiz veya negatif: {fact.source_quote}",
            )
            enriched.append(procedure)
            continue

        updates: dict[str, object] = {}
        surfaces = _parse_tooth_surfaces(item.get("surfaces"))
        if surfaces is None:
            _append_dental_chart_uncertainty(facts, safe_facts, f"Yüzey belirsiz: {fact.source_quote}")
        else:
            updates["surfaces"] = surfaces

        condition = _parse_dental_condition(item.get("condition"))
        if condition is None and item.get("condition") is not None:
            _append_dental_chart_uncertainty(facts, safe_facts, f"Kondisyon belirsiz: {fact.source_quote}")
        elif condition is not None:
            updates["condition"] = condition

        tooth_fdi = _parse_dental_chart_fdi(item.get("tooth_fdi"), fact)
        if tooth_fdi is None:
            updates["tooth_number_fdi"] = None
            updates["dentition"] = None
            updates["tooth_type"] = None
            updates["tooth_group"] = None
            if fact.tooth_number_fdi is not None:
                _append_dental_chart_uncertainty(
                    facts,
                    safe_facts,
                    f"FDI doğrulaması başarısız: {fact.source_quote}",
                )
        else:
            dentition, tooth_type, tooth_group = derive_fdi_classification(tooth_fdi)
            updates["tooth_number_fdi"] = tooth_fdi
            updates["dentition"] = dentition
            updates["tooth_type"] = tooth_type
            updates["tooth_group"] = tooth_group

        enriched.append(procedure.model_copy(update=updates) if updates else procedure)

    return enriched


def _enforce_perio_summary_invariant(summary: ToothPerioSummary) -> ToothPerioSummary:
    """Deterministically reject furcation on an ineligible FDI tooth.

    This guard deliberately does not trust prompt compliance. It also avoids
    logging dictated clinical text; the FDI number is sufficient to make the
    model-output anomaly observable.
    """
    dentition, tooth_type, _ = derive_fdi_classification(summary.tooth_number_fdi)
    tooth_position = summary.tooth_number_fdi % 10
    # Compare stable enum values rather than object identity so the invariant
    # remains deterministic even in test/dev processes that reload modules.
    dentition_value = getattr(dentition, "value", dentition)
    tooth_type_value = getattr(tooth_type, "value", tooth_type)
    is_first_permanent_premolar = (
        dentition_value == "permanent"
        and tooth_type_value == "premolar"
        and tooth_position == 4
    )
    is_furcation_eligible = tooth_type_value == "molar" or is_first_permanent_premolar

    if not is_furcation_eligible and (
        summary.furcation_grade is not None or summary.furcation_site is not None
    ):
        logger.warning(
            "perio_summary_invariant_corrected: tooth_number_fdi=%s "
            "reason=furcation_not_valid_for_tooth_type",
            summary.tooth_number_fdi,
        )
        return summary.model_copy(
            update={"furcation_grade": None, "furcation_site": None}
        )
    return summary


def extract_perio_tooth_summaries(
    dictation: str, llm: LLMProvider
) -> tuple[list[ToothPerioSummary], list[str]]:
    """Extract isolated tooth-level perio summaries and enforce invariants.

    This stage is intentionally not connected to the orchestrator yet. Every
    parsed LLM item passes through `_enforce_perio_summary_invariant` before it
    can leave this function.
    """
    system_prompt = load_system_prompt(PERIO_TOOTH_SUMMARY_PROMPT_FILE)
    raw_output = llm.complete_structured(
        system_prompt,
        f"Dentist dictation:\n{dictation}",
        PERIO_TOOTH_SUMMARY_RESPONSE_SCHEMA,
    )
    data = json.loads(raw_output)
    if not isinstance(data, dict) or not isinstance(data.get("summaries"), list):
        raise ValueError("perio tooth summary payload geçersiz")

    uncertain_items = data.get("uncertain_items", [])
    if not isinstance(uncertain_items, list) or not all(
        isinstance(item, str) for item in uncertain_items
    ):
        raise ValueError("perio tooth summary uncertain_items geçersiz")

    summaries: list[ToothPerioSummary] = []
    allowed_sites = {"buccal", "lingual", "palatal", "mesial", "distal"}
    for item in data["summaries"]:
        if not isinstance(item, dict):
            raise ValueError("perio tooth summary item dict değil")
        tooth_number = item.get("tooth_number_fdi")
        if not isinstance(tooth_number, int) or not is_valid_fdi_number(tooth_number):
            raise ValueError("perio tooth summary FDI geçersiz")

        mobility_grade = item.get("mobility_grade")
        furcation_grade = item.get("furcation_grade")
        for grade in (mobility_grade, furcation_grade):
            if grade is not None and (not isinstance(grade, int) or not 0 <= grade <= 3):
                raise ValueError("perio tooth summary grade geçersiz")

        furcation_site = item.get("furcation_site")
        if furcation_site is not None and furcation_site not in allowed_sites:
            raise ValueError("perio tooth summary furcation_site geçersiz")

        # model_construct preserves the raw, schema-valid LLM values so the
        # explicit defense-in-depth guard can observe and log violations before
        # correcting them. Grade/FDI/site validation is performed just above.
        summary = ToothPerioSummary.model_construct(
            tooth_number_fdi=tooth_number,
            mobility_grade=mobility_grade,
            furcation_grade=furcation_grade,
            furcation_site=furcation_site,
        )
        summaries.append(_enforce_perio_summary_invariant(summary))

    return summaries, uncertain_items


def extract_perio_site_measurements(
    dictation: str, llm: LLMProvider
) -> tuple[list[PerioMeasurement], list[str]]:
    """Extract multi-tooth six-site measurements without guessing segments."""
    system_prompt = load_system_prompt(PERIO_MULTI_TOOTH_PROMPT_FILE)
    raw_output = llm.complete_structured(
        system_prompt,
        f"Multi-tooth dentist periodontal dictation:\n{dictation}",
        PERIO_SITE_RESPONSE_SCHEMA,
    )
    data = json.loads(raw_output)
    if not isinstance(data, dict) or not isinstance(data.get("tooth_segments"), list):
        raise ValueError("perio site measurement payload geçersiz")

    uncertain_items = data.get("uncertain_items", [])
    if not isinstance(uncertain_items, list) or not all(
        isinstance(item, str) for item in uncertain_items
    ):
        raise ValueError("perio site measurement uncertain_items geçersiz")

    measurements: list[PerioMeasurement] = []
    allowed_site_values = {site.value for site in PerioSite}
    optional_int_fields = ("pocket_depth_mm", "gingival_margin_mm", "recession_mm")
    optional_bool_fields = ("bleeding_on_probing", "plaque")

    for segment in data["tooth_segments"]:
        if not isinstance(segment, dict):
            raise ValueError("perio tooth segment dict değil")
        tooth_number = segment.get("tooth_number_fdi")
        source_quote = segment.get("source_quote")
        segment_uncertain = segment.get("is_uncertain", False)
        sites = segment.get("sites", [])
        if not isinstance(tooth_number, int) or not is_valid_fdi_number(tooth_number):
            raise ValueError("perio tooth segment FDI geçersiz")
        if not isinstance(source_quote, str) or not source_quote:
            raise ValueError("perio tooth segment source_quote eksik")
        if not isinstance(segment_uncertain, bool) or not isinstance(sites, list):
            raise ValueError("perio tooth segment alanları geçersiz")

        values_by_site: dict[PerioSite, dict] = {}
        for site_values in sites:
            if not isinstance(site_values, dict) or site_values.get("site") not in allowed_site_values:
                raise ValueError("perio site geçersiz")
            site = PerioSite(site_values["site"])
            if site in values_by_site:
                raise ValueError("perio site tekrarlı")
            for field in optional_int_fields:
                value = site_values.get(field)
                if value is not None and not isinstance(value, int):
                    raise ValueError(f"perio {field} geçersiz")
            depth = site_values.get("pocket_depth_mm")
            if depth is not None and not 0 <= depth <= 15:
                raise ValueError("perio pocket_depth_mm aralık dışında")
            for field in optional_bool_fields:
                value = site_values.get(field)
                if value is not None and not isinstance(value, bool):
                    raise ValueError(f"perio {field} geçersiz")
            if not isinstance(site_values.get("is_uncertain", False), bool):
                raise ValueError("perio site is_uncertain geçersiz")
            values_by_site[site] = site_values

        for site in PerioSite:
            values = values_by_site.get(site, {})
            recession_mm = values.get("recession_mm")
            measurements.append(
                PerioMeasurement(
                    tooth_number_fdi=tooth_number,
                    site=site,
                    pocket_depth_mm=values.get("pocket_depth_mm"),
                    gingival_margin_mm=_derive_gingival_margin_mm(
                        values.get("gingival_margin_mm"), recession_mm
                    ),
                    bleeding_on_probing=values.get("bleeding_on_probing"),
                    plaque=values.get("plaque"),
                    recession_mm=recession_mm,
                    source_quote=source_quote,
                    is_uncertain=segment_uncertain or values.get("is_uncertain", False),
                )
            )

    return measurements, uncertain_items


def _derive_gingival_margin_mm(
    gingival_margin_mm: Optional[int], recession_mm: Optional[int]
) -> Optional[int]:
    """Normalize recession to the signed CEJ-relative gingival margin."""
    if recession_mm is not None:
        return -recession_mm
    return gingival_margin_mm


def _append_dental_chart_uncertainty(
    original_facts: ClinicalFactsBundle, safe_facts: ClinicalFactsBundle, message: str
) -> None:
    if message not in safe_facts.uncertain_items:
        safe_facts.uncertain_items.append(message)
    if message not in original_facts.uncertain_items:
        original_facts.uncertain_items.append(message)


def _build_dental_chart_user_input(fact: ClinicalFact) -> str:
    payload = {
        "fact": {
            "category": fact.category.value,
            "text": fact.text,
            "source_role": fact.source_role.value,
            "tooth_number_fdi": fact.tooth_number_fdi,
            "status": fact.status.value if fact.status else None,
            "source_quote": fact.source_quote,
            "is_uncertain": fact.is_uncertain,
        }
    }
    return "Procedure fact:\n" + json.dumps(payload, ensure_ascii=False)


def _loads_llm_json_array(raw_output: str) -> list[object]:
    data = _loads_llm_json_object(raw_output)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        items = _first_present(data, ("items", "commands", "procedures"), default=[])
        if isinstance(items, list):
            return items
    raise ValueError("dental chart payload array değil")


def _normalize_dental_chart_payload(data: list[object]) -> list[dict]:
    normalized: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("dental chart item dict değil")
        normalized.append(
            {
                "tooth_fdi": _first_present(item, ("tooth_fdi", "tooth_number_fdi", "fdi"), default=None),
                "surfaces": _first_present(item, ("surfaces", "surface"), default=None),
                "condition": _first_present(item, ("condition", "dental_condition"), default=None),
                "status": _first_present(item, ("status",), default=None),
                "source_quote": _first_present(item, ("source_quote", "quote"), default=None),
            }
        )
    return normalized


def _select_dental_chart_item(items: list[dict], fact: ClinicalFact) -> Optional[dict]:
    for item in items:
        quote = item.get("source_quote")
        if isinstance(quote, str) and quote and quote in fact.source_quote:
            return item
    return items[0] if items else None


def _parse_tooth_surfaces(value: object) -> Optional[list[ToothSurface]]:
    if value is None:
        return None
    raw_values = value if isinstance(value, list) else [value]
    surfaces: list[ToothSurface] = []
    for raw in raw_values:
        if raw is None:
            return None
        try:
            surface = ToothSurface(str(raw).upper())
        except ValueError:
            return None
        if surface not in surfaces:
            surfaces.append(surface)
    return surfaces


def _parse_dental_condition(value: object) -> Optional[DentalCondition]:
    if value is None:
        return None
    try:
        return DentalCondition(str(value).casefold())
    except ValueError:
        return None


def _parse_dental_chart_fdi(value: object, fact: ClinicalFact) -> Optional[int]:
    try:
        candidate = int(value) if value is not None else fact.tooth_number_fdi
    except (TypeError, ValueError):
        return None
    if candidate is None or not _is_valid_fdi(candidate):
        return None
    if fact.tooth_number_fdi is not None and candidate != fact.tooth_number_fdi:
        return None
    return candidate


def _detect_procedure_family(fact: ClinicalFact) -> Optional[str]:
    fact_text = _normalize_lookup_text(fact.text)
    text = _procedure_text(fact)

    if _is_negated_procedure_text(text):
        return None

    if _has_any(fact_text, ("kanal tedavisi", "endodontik tedavi")):
        return "kanal_tedavisi"

    if _has_any(fact_text, ("geçici", "gecici")) and _has_any(
        fact_text, ("dolgu", "restorasyon")
    ):
        return "gecici_restorasyon"

    if "kompozit" in fact_text:
        return "kompozit_dolgu"

    if _has_any(text, ("kompozit", "dolgu", "restorasyon")):
        if _has_any(text, ("geçici", "gecici")):
            return "gecici_restorasyon"
        if "kompozit" in text:
            return "kompozit_dolgu"
        if "dolgu" in text:
            return "kompozit_dolgu"

    if _has_any(text, ("kanal tedavisi", "endodontik tedavi")):
        return "kanal_tedavisi"

    if _has_any(text, ("diş çekimi", "dis cekimi", "çekim", "cekim")):
        return "dis_cekimi"

    if _has_any(text, ("detertraj", "diş taşı", "dis tasi", "diştaşı", "distasi")):
        return "detertraj"

    if _has_any(text, ("periapikal röntgen", "periapikal rontgen")):
        return "periapikal_rontgen"

    if _has_any(text, ("panoramik film", "panoramik röntgen", "panoramik rontgen")):
        return "panoramik_film"

    return None


def _detect_surface_count(fact: ClinicalFact) -> SurfaceCount | None:
    text = _procedure_text(fact)
    if _has_any(text, ("tek yüz", "tek yuz", "bir yüz", "bir yuz")):
        return SurfaceCount.ONE_SURFACE
    if _has_any(text, ("iki yüz", "iki yuz", "2 yüz", "2 yuz")):
        return SurfaceCount.TWO_SURFACE
    if _has_any(text, ("üç yüz", "uc yuz", "üç yuz", "3 yüz", "3 yuz")):
        return SurfaceCount.THREE_SURFACE
    if "kompozit" in text or "dolgu" in text:
        return SurfaceCount.UNCLEAR
    return None


def _detect_canal_count(fact: ClinicalFact) -> CanalCount | None:
    text = _procedure_text(fact)
    if _has_any(text, ("tek kanal", "bir kanal", "1 kanal")):
        return CanalCount.ONE_CANAL
    if _has_any(text, ("iki kanal", "2 kanal")):
        return CanalCount.TWO_CANAL
    if _has_any(text, ("üç kanal", "uc kanal", "3 kanal")):
        return CanalCount.THREE_CANAL
    if _has_any(text, ("kanal tedavisi", "endodontik tedavi")):
        return CanalCount.UNCLEAR
    return None


def _detect_treatment_kind(fact: ClinicalFact) -> TreatmentKind:
    text = _procedure_text(fact)
    if _has_any(
        text,
        (
            "retreatment",
            "yeniden kanal",
            "kanal yenile",
            "kanal tedavisi yenile",
            "revizyon",
            "tekrar kanal",
        ),
    ):
        return TreatmentKind.RETREATMENT
    return TreatmentKind.INITIAL


def _procedure_text(fact: ClinicalFact) -> str:
    return _normalize_lookup_text(f"{fact.text} {fact.source_quote}")


def _normalize_lookup_text(text: str) -> str:
    return text.casefold().replace("i̇", "i")


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _is_negated_procedure_text(text: str) -> bool:
    return _has_any(
        text,
        (
            "gündemde değil",
            "gundemde degil",
            "planlanmadı",
            "planlanmadi",
            "yapılmayacak",
            "yapilmayacak",
            "çekim yok",
            "cekim yok",
        ),
    )


def _is_valid_optional_fdi(tooth_number: Optional[int]) -> bool:
    return tooth_number is None or _is_valid_fdi(tooth_number)


def match_codes_and_checklist(
    procedures: list[ProcedureObject],
    facts: Optional[ClinicalFactsBundle] = None,
    llm: Optional[LLMProvider] = None,
) -> list[CodeSuggestionBundle]:
    """Pipeline kapısı: fact invariant'ını uygula, TDB matcher'a delege et."""
    safe_facts = _enforce_source_role_invariant(facts) if facts is not None else None
    return _tdb_match_codes_and_checklist(procedures, safe_facts, llm)
