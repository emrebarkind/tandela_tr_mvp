"""
Pipeline aşamaları.

V1'de bu modüldeki fonksiyonların ÇOĞU hâlâ STUB'tır (gerçek ASR/LLM/DB
çağrısı yapmaz) — ama `assign_roles` artık İSTİSNA: gerçek bir LLM çağrısı
yapar (vendor TBD, `LLMProvider` arabirimi arkasında — CLAUDE.md §6/§10).
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
- extract_clinical_facts:     clinical_facts_extraction LLM prompt'u (henüz stub)
- generate_clinical_note:     clinical_note_generation LLM prompt'u (henüz stub)
- extract_procedures:         fact JSON'undan + FDI normalize/doğrulama
- match_codes_and_checklist:  deterministik TDB DB araması (tdb/) + LLM açıklama katmanı
"""

from __future__ import annotations

import json
import logging

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
    FactCategory,
    NoteSentence,
    ProcedureObject,
    CodeSuggestionBundle,
)
from app.prompts.loader import load_system_prompt
from app.providers.audio_processing import AudioProcessingProvider
from app.providers.llm import LLMProvider

logger = logging.getLogger(__name__)

ROLE_ASSIGNMENT_PROMPT_FILE = "role_assignment.md"

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
            role=role_by_speaker[u.speaker_id],
            text=u.text,
            start_sec=u.start_sec,
            end_sec=u.end_sec,
        )
        for u in transcript.utterances
        if u.speaker_id in role_by_speaker
    ]
    return RoleLabelledTranscript(session_id=transcript.session_id, utterances=utterances)


def extract_clinical_facts(transcript: RoleLabelledTranscript) -> ClinicalFactsBundle:
    """STUB: gerçek clinical_facts_extraction LLM çağrısı yok.

    Boş bundle döner — uydurma fact YOK (CLAUDE.md §4.1, §4.6). Gerçek
    implementasyon prompts/clinical_facts_extraction.md ile değiştirilir.
    """
    return ClinicalFactsBundle(session_id=transcript.session_id, facts=[], uncertain_items=[])


def generate_clinical_note(facts: ClinicalFactsBundle) -> ClinicalNoteDraft:
    """STUB: gerçek clinical_note_generation LLM çağrısı yok (içerik üretimi
    yok), ama YAPISAL kontrat tamdır.

    Kontrat (CLAUDE.md aşama 2→3): yalnızca `facts`'ten üretir, yeni bilgi
    eklemez, PARAPHRASE ETMEZ — her `NoteSentence.text` ilgili fact'in
    `text`'i, `source_quote`/`source_role` o fact'ten DEĞİŞMEDEN taşınır.

    Invariant (CLAUDE.md §4.2) burada BAĞIMSIZ olarak da uygulanır:
    `_enforce_source_role_invariant` upstream extraction'a güvenmeden,
    dentist olmayan source_role'den gelen clinical_findings/assessment/
    treatment_plan fact'lerini not'a bulgu olarak girmeden önce yeniden
    kategorize eder/eler.
    """
    safe_facts = _enforce_source_role_invariant(facts)

    sections: dict[str, list[NoteSentence]] = {section: [] for section in _CATEGORY_TO_NOTE_SECTION.values()}
    for idx, fact in enumerate(safe_facts.facts):
        section = _CATEGORY_TO_NOTE_SECTION.get(fact.category)
        if section is None:
            continue
        sections[section].append(
            NoteSentence(
                sentence_id=f"s{idx}",
                text=fact.text,
                source_role=fact.source_role,
                source_quote=fact.source_quote,
            )
        )

    return ClinicalNoteDraft(
        session_id=safe_facts.session_id,
        uncertain_items=list(safe_facts.uncertain_items),
        **sections,
    )


def extract_procedures(facts: ClinicalFactsBundle) -> list[ProcedureObject]:
    """STUB: gerçek procedure extraction + FDI normalize/doğrulama yok.

    Invariant (CLAUDE.md §4.2) burada da BAĞIMSIZ olarak uygulanır — bu adım
    şu an stub olduğu için sonuç gözle görünür şekilde değişmez (hâlâ `[]`
    döner), ama sözleşme şimdiden kurulur: ileride procedure'ler facts'ten
    türetilirken, dentist olmayan source_role'den gelen clinical_findings/
    assessment/treatment_plan fact'leri asla doğrudan procedure kanıtı
    olarak kullanılmaz.
    """
    _enforce_source_role_invariant(facts)
    return []


def match_codes_and_checklist(procedures: list[ProcedureObject]) -> list[CodeSuggestionBundle]:
    """STUB: gerçek deterministik TDB DB araması + checklist değerlendirme +
    LLM açıklama katmanı yok. Bkz. docs/tdb-code-matching-spec.md §3 (Katman C)."""
    return []
