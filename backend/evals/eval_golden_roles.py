"""
eval_golden_roles.py — docs/golden-set.md'nin 4 senaryosunu GERÇEK Gemini ile
çalıştırır (role_assignment + clinical_facts_extraction +
clinical_note_generation katmanları).
procedure extraction katmanı deterministik olduğu için aynı eval raporunda
facts sonrası ayrıca kontrol edilir.

>>> CI'A KOYULMAZ. Manuel/ara sıra çalıştırılır:
>>>   GEMINI_API_KEY backend/.env'de (ya da export edilmiş) olmalı.
>>>   cd backend && python -m evals.eval_golden_roles
>>>
>>> Neden CI'da değil: (1) olasılıksal — aynı prompt model versiyonuna/run'a
>>> göre farklı çıktı verebilir, deterministik bir CI gate'i olamaz; (2) her
>>> çalıştırma gerçek API çağrısı = maliyet. Kontrat/regresyon testleri
>>> (`ScriptedLLM` ile, deterministik) ayrı script'lerde yaşıyor — bu dosya
>>> SADECE model doğruluğunu (eval) ölçer.

Bu script `verify_golden_set.py`'den (ScriptedLLM ile, deterministik kontrat
testi) FARKLIDIR: orada fixture = sonucu belirliyordu, burada gerçek model
transkripti okuyup KENDİ tahminini üretiyor. golden-set.md'nin "eval harness
sözleşmesi"ne göre BİREBİR metin eşleşmesi ARANMAZ — yalnızca role/status/
manual_review_required/requires_role_review hedefleri; facts için category/
source_role/source_speaker/tooth_number_fdi/status/is_uncertain/source_quote
hedefleri; note için fact text/source_quote/source_role değerlerinin doğru
bölümlere birebir taşınması; procedure extraction için procedure_family/FDI/
status/yüzey-kanal alanları; ve MUST NOT negatifleri kontrol edilir. `reason`
ve fact `text` gibi serbest metin alanları insan/gevşek kontrol için ekrana
basılır, assert edilmez.

§4.8 floor notu: docs/golden-set.md S3/S4'te B (hasta, tek-ifadeli) "clear"
olarak belirtilmiştir ama `stages.assign_roles` kod tarafında tek-ifadeli bir
konuşmacıyı ASLA `clear` bırakmaz (CLAUDE.md §4.8) — model ne derse desin
`review_needed`'e düşürülür. Bu yüzden burada "ham model durumu" ile "floor
uygulanmış efektif beklenen durum" AYRI raporlanır; floor uygulanması bir
hata değil, kodun kasıtlı güvenlik tabanıdır.
"""

from __future__ import annotations

import json
import traceback

from google.genai import errors as genai_errors

from app.pipeline import stages
from app.pipeline.types import (
    DentistRole,
    FactCategory,
    CanalCount,
    ChecklistItemStatus,
    CodeMatchState,
    ProcedureStatus,
    RoleAssignmentResult,
    RoleStatus,
    SpeakerLabelledTranscript,
    SpeakerRoleAssignment,
    SurfaceCount,
    Utterance,
)
from app.prompts.loader import load_system_prompt
from app.providers.gemini_provider import GeminiLLMProvider

# ---------------------------------------------------------------------------
# Senaryolar — docs/golden-set.md ile 1:1 (transkript + beklenen hedefler).
# golden-set.md değişirse bu liste de güncellenmeli (tek kaynak orada, burası
# eval için kopyası).
# ---------------------------------------------------------------------------


def _t(session_id: str, lines: list[tuple[str, str]]) -> SpeakerLabelledTranscript:
    return SpeakerLabelledTranscript(
        session_id=session_id,
        utterances=[
            Utterance(speaker_id=sid, text=text, start_sec=float(i), end_sec=float(i) + 1.0)
            for i, (sid, text) in enumerate(lines)
        ],
    )


SCENARIOS = [
    {
        "name": "S1",
        "session_id": "golden-s1",
        "lines": [
            ("A", "Merhaba, şikayetiniz nedir?"),
            ("B", "Sağ alt tarafta iki gündür ağrım var, özellikle yemek yerken zonkluyor."),
            ("A", "Ağzınızı açın lütfen. Sağ alt altıda, yani 46 numarada derin çürük görüyorum."),
            ("C", "Hocam röntgeni açıyorum."),
            ("A", "Perküsyonda hassasiyet var. Kanal tedavisi gerekebilir. Bugün geçici dolgu yapıp kanal tedavisi planlayalım."),
            ("B", "Benim dişim iltihaplı mı yani?"),
            ("A", "Röntgene göre periapikal bölgede şüpheli bir görüntü var, kesin değerlendirme için endodontik muayeneyle ilerleyeceğiz."),
            ("A", "46 numara için kanal tedavisi planlandı, geçici restorasyon yapılacak."),
        ],
        "expected": {
            "A": {"role": "dentist", "status": "clear"},
            "B": {"role": "patient", "status": "clear"},
            "C": {"role": "assistant_or_other", "status": "review_needed"},
        },
        "expected_manual_review_required": True,
        "expect_gate_blocks": True,
        "must_not": [],  # role katmanına özgü ekstra negatif yok (facts katmanı için ayrı)
        "expected_facts_after_role_approval": [
            {
                "category": "patient_complaint",
                "source_role": "patient",
                "source_speaker": "B",
                "tooth_number_fdi": None,
                "status": None,
                "is_uncertain": False,
                "quote_fragments": ["Sağ alt tarafta iki gündür ağrım var"],
            },
            {
                "category": "patient_complaint",
                "source_role": "patient",
                "source_speaker": "B",
                "tooth_number_fdi": None,
                "status": None,
                "is_uncertain": False,
                "quote_fragments": ["Benim dişim iltihaplı mı yani?"],
            },
            {
                "category": "clinical_findings",
                "source_role": "dentist",
                "source_speaker": "A",
                "tooth_number_fdi": 46,
                "status": None,
                "is_uncertain": False,
                "quote_fragments": ["46 numarada derin çürük görüyorum"],
            },
            {
                "category": "clinical_findings",
                "source_role": "dentist",
                "source_speaker": "A",
                "tooth_number_fdi": 46,
                "status": None,
                "is_uncertain": False,
                "quote_fragments": ["Perküsyonda hassasiyet var"],
            },
            {
                "category": "clinical_findings",
                "source_role": "dentist",
                "source_speaker": "A",
                "tooth_number_fdi": 46,
                "status": None,
                "is_uncertain": True,
                "quote_fragments": ["periapikal bölgede şüpheli bir görüntü var"],
            },
            {
                "category": "treatment_plan",
                "source_role": "dentist",
                "source_speaker": "A",
                "tooth_number_fdi": 46,
                "status": None,
                "is_uncertain": False,
                "quote_fragments": ["46 numara için kanal tedavisi planlandı"],
            },
            {
                "category": "procedures",
                "source_role": "dentist",
                "source_speaker": "A",
                "tooth_number_fdi": 46,
                "status": "planned",
                "is_uncertain": False,
                "quote_fragments": ["kanal tedavisi planlandı"],
            },
            {
                "category": "procedures",
                "source_role": "dentist",
                "source_speaker": "A",
                "tooth_number_fdi": 46,
                "status": "unclear",
                "is_uncertain": True,
                "quote_fragments": ["geçici", "yap"],
            },
        ],
        "expected_uncertain_fragments": ["Geçici", "çeliş"],
        "facts_must_not": ["definite_infection", "patient_finding", "drop_patient_infection_worry", "temporary_restoration_decided", "c_fact", "wrong_fdi_46"],
        "expected_procedures_after_role_approval": [
            {
                "procedure_family": "kanal_tedavisi",
                "tooth_number_fdi": 46,
                "status": "planned",
                "surface_count": None,
                "canal_count": "unclear",
                "quote_fragments": ["kanal tedavisi planlandı"],
            },
            {
                "procedure_family": "gecici_restorasyon",
                "tooth_number_fdi": 46,
                "status": "unclear",
                "surface_count": "unclear",
                "canal_count": None,
                "quote_fragments": ["geçici", "yap"],
            },
        ],
        "expected_code_suggestions_after_role_approval": [
            {
                "candidate_count": 3,
                "match_states": ["ambiguous_multiple_candidates"],
                "checklist": {
                    "tooth_number": "found",
                    "canal_count": "review",
                    "endo_diagnosis": "found",
                    "status": "found",
                },
            },
            {
                "candidate_count": 1,
                "match_states": ["needs_review"],
                "checklist": {
                    "tooth_number": "found",
                    "status": "review",
                },
            },
        ],
    },
    {
        "name": "S2",
        "session_id": "golden-s2",
        "lines": [
            ("A", "Bugün hangi dişten şikayetçiydiniz?"),
            ("B", "Üst sağ tarafta bir dişimde hassasiyet vardı, soğukta artıyordu."),
            ("A", "Şey numaralı dişte... yirmi... yirmi altı mı, tam okunmuyor, neyse üst sağ bölgede çürük var. İki yüzlü kompozit dolgu yaptık bugün."),
            ("B", "Tamam, teşekkürler."),
        ],
        "expected": {
            "A": {"role": "dentist", "status": "clear"},
            "B": {"role": "patient", "status": "clear"},
        },
        "expected_manual_review_required": False,
        "expect_gate_blocks": False,
        "must_not": [],
        "expected_facts_after_role_approval": [
            {
                "category": "patient_complaint",
                "source_role": "patient",
                "source_speaker": "B",
                "tooth_number_fdi": None,
                "status": None,
                "is_uncertain": False,
                "quote_fragments": ["Üst sağ tarafta bir dişimde hassasiyet vardı, soğukta artıyordu"],
            },
            {
                "category": "clinical_findings",
                "source_role": "dentist",
                "source_speaker": "A",
                "tooth_number_fdi": None,
                "status": None,
                "is_uncertain": True,
                "quote_fragments": ["üst sağ bölgede çürük var"],
            },
            {
                "category": "procedures",
                "source_role": "dentist",
                "source_speaker": "A",
                "tooth_number_fdi": None,
                "status": "performed",
                "is_uncertain": False,
                "quote_fragments": ["İki yüzlü kompozit dolgu yaptık bugün"],
            },
        ],
        "expected_uncertain_fragments": ["Diş numarası", "yüzey"],
        "facts_must_not": ["assign_mumbled_26", "performed_not_preserved"],
        "expected_procedures_after_role_approval": [
            {
                "procedure_family": "kompozit_dolgu",
                "tooth_number_fdi": None,
                "status": "performed",
                "surface_count": "two_surface",
                "canal_count": None,
                "quote_fragments": ["İki yüzlü kompozit dolgu yaptık bugün"],
            },
        ],
        "expected_code_suggestions_after_role_approval": [
            {
                "candidate_count": 1,
                "match_states": ["insufficient_documentation"],
                "checklist": {
                    "tooth_number": "missing",
                    "surface_names": "missing",
                    "indication": "found",
                    "material": "found",
                    "status": "found",
                },
            },
        ],
    },
    {
        "name": "S3",
        "session_id": "golden-s3",
        "lines": [
            ("A", "Şikayetiniz neydi, ne zaman başladı?"),
            ("B", "Birkaç gündür sol üstte ağrı var."),
            ("A", "Bakalım... sol üst birde hafif çürük görünüyor, ileri bir bulgu yok."),
            ("C", "Bence mineye kadar inmiş, kontrol edelim."),
        ],
        "expected": {
            "A": {"role": "dentist", "status": "clear"},
            "B": {"role": "patient", "status": "clear"},
            # Güncelleme notu (bkz. docs/golden-set.md S3): önceki hedef
            # "unknown" idi; "klinik konuşan = rolü tam belirsiz" varsayımı
            # fazla ihtiyatlıydı. C muayeneyi yönetmiyor/nihai planı
            # belirlemiyor → assistant_or_other (tek-ifade → review_needed,
            # gate yine bloke eder). Gerçek model çıktısıyla doğrulandı.
            "C": {"role": "assistant_or_other", "status": "review_needed"},
        },
        "expected_manual_review_required": True,
        "expect_gate_blocks": True,
        # golden-set.md MUST NOT: "C'ye varsayımla dentist atayıp devam etmek."
        "must_not": [("C_not_dentist", lambda by_speaker: by_speaker["C"].role != DentistRole.DENTIST)],
        "expected_facts_after_role_approval": None,
        "facts_must_not": ["facts_generated_while_gate_blocked"],
        "expected_procedures_after_role_approval": None,
        "expected_code_suggestions_after_role_approval": None,
    },
    {
        "name": "S4",
        "session_id": "golden-s4",
        "lines": [
            ("A", "Bu dişle ilgili daha önce bir işlem yapıldı mı?"),
            ("B", "Evet, geçen sene bu dişe kanal tedavisi yapılmıştı, ama yine ağrımaya başladı."),
            ("A", "Anladım. 36 numarada eski kanal tedavisi mevcut, periapikalde genişleme var. Retreatment değerlendireceğiz."),
            ("C", "Kesinlikle enfeksiyon var, hemen çekmek lazım."),
            ("A", "Şimdilik retreatment planlıyoruz, çekim gündemde değil."),
        ],
        "expected": {
            "A": {"role": "dentist", "status": "clear"},
            "B": {"role": "patient", "status": "clear"},
            "C": {"role": "assistant_or_other", "status": "review_needed"},
        },
        "expected_manual_review_required": True,
        "expect_gate_blocks": True,
        "must_not": [],
        "expected_facts_after_role_approval": [
            {
                "category": "history",
                "source_role": "patient",
                "source_speaker": "B",
                "tooth_number_fdi": None,
                "status": None,
                "is_uncertain": False,
                "quote_fragments": ["geçen sene bu dişe kanal tedavisi yapılmıştı"],
            },
            {
                "category": "patient_complaint",
                "source_role": "patient",
                "source_speaker": "B",
                "tooth_number_fdi": None,
                "status": None,
                "is_uncertain": False,
                "quote_fragments": ["yine ağrımaya başladı"],
            },
            {
                "category": "clinical_findings",
                "source_role": "dentist",
                "source_speaker": "A",
                "tooth_number_fdi": 36,
                "status": None,
                "is_uncertain": False,
                "quote_fragments": ["36 numarada eski kanal tedavisi mevcut", "periapikalde genişleme var"],
            },
            {
                "category": "treatment_plan",
                "source_role": "dentist",
                "source_speaker": "A",
                "tooth_number_fdi": 36,
                "status": None,
                "is_uncertain": False,
                "quote_fragments": ["Şimdilik retreatment planlıyoruz", "çekim gündemde değil"],
            },
        ],
        "expected_uncertain_fragments": [],
        "facts_must_not": ["patient_past_procedure_as_procedure", "assistant_assessment_or_plan", "extraction_planned"],
        "expected_procedures_after_role_approval": [],
        "expected_code_suggestions_after_role_approval": [],
    },
    {
        "name": "S5",
        "session_id": "golden-s5",
        "lines": [
            ("A", "Merhaba, bugün ne şikayetiniz var?"),
            ("B", "Sol üst tarafta yaklaşık bir haftadır ağrı var, özellikle sıcak yiyecek yiyince artıyor."),
            ("A", "Ağzınızı açar mısınız? Sol üst yedi numarada derin çürük görüyorum, gingival kenara yakın."),
            ("A", "Röntgende pulpaya yakın bir görüntü var, kesin olarak söylemek zor ama kanal tedavisi gerekebilir."),
            ("B", "Yani dişimi çekmeniz gerekmeyecek değil mi?"),
            ("A", "Hayır, şu an çekim düşünmüyoruz. Önce kanal tedavisini deneyelim, başarısız olursa değerlendiririz."),
            ("A", "Bugün geçici dolgu yapalım, önümüzdeki hafta kanal tedavisine başlarız."),
            ("B", "Peki sağ tarafımda da hafif bir hassasiyet var, geçen ay kompozit dolgu yaptırmıştım oradan."),
            ("A", "Sağ üst altı numarada iki yüzlü kompozit dolgu var, aşınma yok gibi görünüyor, şimdilik bir işlem gerekmiyor, takip edelim."),
            ("A", "Sol üst yedi numara için kanal tedavisi planlandı, bugün geçici dolgu yapıldı."),
        ],
        "expected": {
            "A": {"role": "dentist", "status": "clear"},
            "B": {"role": "patient", "status": "clear"},
        },
        "expected_manual_review_required": False,
        "expect_gate_blocks": False,
        "must_not": [],
        "expected_facts_after_role_approval": [
            {
                "category": "patient_complaint",
                "source_role": "patient",
                "source_speaker": "B",
                "tooth_number_fdi": None,
                "status": None,
                "is_uncertain": False,
                "quote_fragments": ["Sol üst tarafta yaklaşık bir haftadır ağrı var", "sıcak yiyecek yiyince artıyor"],
            },
            {
                "category": "clinical_findings",
                "source_role": "dentist",
                "source_speaker": "A",
                "tooth_number_fdi": 27,
                "status": None,
                "is_uncertain": False,
                "quote_fragments": ["Sol üst yedi numarada derin çürük görüyorum", "gingival kenara yakın"],
            },
            {
                "category": "assessment",
                "source_role": "dentist",
                "source_speaker": "A",
                "tooth_number_fdi": 27,
                "status": None,
                "is_uncertain": True,
                "quote_fragments": ["kesin olarak söylemek zor", "kanal tedavisi gerekebilir"],
            },
            {
                "category": "patient_complaint",
                "source_role": "patient",
                "source_speaker": "B",
                "tooth_number_fdi": None,
                "status": None,
                "is_uncertain": False,
                "quote_fragments": ["dişimi çekmeniz gerekmeyecek değil mi"],
            },
            {
                "category": "treatment_plan",
                "source_role": "dentist",
                "source_speaker": "A",
                "tooth_number_fdi": 27,
                "status": None,
                "is_uncertain": False,
                "quote_fragments": ["çekim düşünmüyoruz", "kanal tedavisini deneyelim"],
            },
            {
                "category": "procedures",
                "source_role": "dentist",
                "source_speaker": "A",
                "tooth_number_fdi": 27,
                "status": "planned",
                "is_uncertain": False,
                "quote_fragments": ["kanal tedavisi planlandı"],
            },
            {
                "category": "procedures",
                "source_role": "dentist",
                "source_speaker": "A",
                "tooth_number_fdi": 27,
                "status": "performed",
                "is_uncertain": False,
                "quote_fragments": ["bugün geçici dolgu yapıldı"],
            },
            {
                "category": "patient_complaint",
                "source_role": "patient",
                "source_speaker": "B",
                "tooth_number_fdi": None,
                "status": None,
                "is_uncertain": False,
                "quote_fragments": ["sağ tarafımda da hafif bir hassasiyet var"],
            },
            {
                "category": "history",
                "source_role": "patient",
                "source_speaker": "B",
                "tooth_number_fdi": None,
                "status": None,
                "is_uncertain": False,
                "quote_fragments": ["geçen ay kompozit dolgu yaptırmıştım"],
            },
            {
                "category": "clinical_findings",
                "source_role": "dentist",
                "source_speaker": "A",
                "tooth_number_fdi": 16,
                "status": None,
                "is_uncertain": True,
                "quote_fragments": ["Sağ üst altı numarada iki yüzlü kompozit dolgu var", "aşınma yok gibi görünüyor"],
            },
            {
                "category": "treatment_plan",
                "source_role": "dentist",
                "source_speaker": "A",
                "tooth_number_fdi": 16,
                "status": None,
                "is_uncertain": False,
                "quote_fragments": ["şimdilik bir işlem gerekmiyor", "takip edelim"],
            },
        ],
        "expected_uncertain_fragments": [],
        "facts_must_not": [
            "extraction_planned",
            "s5_definite_rct",
            "s5_right_composite_current_procedure",
            "s5_wrong_fdi",
        ],
        "expected_procedures_after_role_approval": [
            {
                "procedure_family": "kanal_tedavisi",
                "tooth_number_fdi": 27,
                "status": "planned",
                "surface_count": None,
                "canal_count": "unclear",
                "quote_fragments": ["kanal tedavisi planlandı"],
            },
            {
                "procedure_family": "gecici_restorasyon",
                "tooth_number_fdi": 27,
                "status": "performed",
                "surface_count": "unclear",
                "canal_count": None,
                "quote_fragments": ["bugün geçici dolgu yapıldı"],
            },
        ],
        "expected_code_suggestions_after_role_approval": None,
    },
]


def _effective_expected_status(expected_status: str, utterance_count: int) -> RoleStatus:
    """golden-set.md hedefi + CLAUDE.md §4.8 floor birleşimi (bkz. modül
    docstring'i). Floor uygulanmadıysa golden-set.md'nin dediği aynen kalır."""
    if utterance_count <= 1 and expected_status == "clear":
        return RoleStatus.REVIEW_NEEDED
    return RoleStatus(expected_status)


def _debug_raw_call_s1(llm: GeminiLLMProvider) -> None:
    """DEBUG-ONLY (geçici teşhis aracı — kalıcı eval mantığı değil).

    `stages.assign_roles` üretim kodu LLM/parse hatasını fail-safe'e
    düşürerek YUTAR (CLAUDE.md §4.1 — bu doğru davranış, BURADA
    DEĞİŞTİRİLMEZ/tekrarlanmaz). Bu fonksiyon assign_roles'u atlayıp
    `llm.complete()`'i S1 için DOĞRUDAN çağırır, amaç: fail-safe'e düşmeden
    ÖNCE model boş mu dönüyor, geçersiz JSON mu, yoksa geçerli JSON ama
    beklenen alan adlarımızla uyuşmuyor mu — bunu ayırt etmek.

    GEMINI_API_KEY değeri hiçbir koşulda burada basılmaz/loglanmaz.
    """
    s1 = SCENARIOS[0]
    assert s1["name"] == "S1"
    transcript = _t(s1["session_id"], s1["lines"])

    system_prompt = load_system_prompt(stages.ROLE_ASSIGNMENT_PROMPT_FILE)
    user_input = stages._build_role_assignment_user_input(transcript)

    print("=" * 70)
    print("DEBUG (S1) — fail-safe'den ÖNCE ham GeminiLLMProvider.complete() çıktısı")
    print(f"  model: {llm.model}")
    print("-" * 70)

    try:
        raw = llm.complete(system_prompt, user_input)
    except Exception as exc:  # noqa: BLE001 — teşhis amaçlı, görünür şekilde raporla
        print(f"  complete() EXCEPTION fırlattı: {type(exc).__name__}: {exc}")
        if isinstance(exc, genai_errors.APIError):
            print(
                "  Bu bir google.genai.errors.APIError — Gemini API GERÇEKTEN "
                "yanıt verdi (non-2xx). HTTP durumu:"
            )
            print(f"    code={exc.code!r} status={exc.status!r} message={exc.message!r}")
        else:
            print(
                "  Bu google.genai.errors.APIError DEĞİL → Gemini'den hiçbir HTTP "
                "yanıtı ALINMADI (transport/proxy seviyesinde hata olabilir); bu "
                "durumda Gemini tarafında raporlanacak bir HTTP durum kodu YOKTUR — "
                "aşağıdaki exception, ulaşılan en derin/yakın hatadır:"
            )
            cause = exc.__cause__
            if cause is not None:
                print(f"    __cause__: {type(cause).__name__}: {cause}")
        print("=" * 70)
        return

    if raw == "":
        print("  complete() BOŞ STRING döndürdü (model hiçbir içerik üretmedi).")
        print("=" * 70)
        return

    print(f"  HAM STRING ({len(raw)} karakter):")
    print(f"    {raw!r}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"  JSON PARSE HATASI (geçersiz JSON): {exc}")
        print("=" * 70)
        return

    print("  JSON parse OK. Parsed içerik:")
    print(f"    {data!r}")

    missing = [k for k in ("assignments", "manual_review_required") if k not in data]
    if missing:
        print(f"  Geçerli JSON ama BEKLENEN ÜST SEVİYE ALANLAR EKSİK: {missing}")
    else:
        print("  Beklenen üst seviye alanlar (assignments, manual_review_required) MEVCUT.")
    print("=" * 70)


def _dentist_approved_roles(scenario: dict, transcript: SpeakerLabelledTranscript) -> RoleAssignmentResult:
    """Gate'te bloke olan ama docs/golden-set.md'de "hekim rol onayından sonra
    facts beklenir" denen senaryolar için simülasyon.

    Hekim onayı sonrası tek-ifadeli konuşmacıların `clear` olabilmesi normaldir:
    artık bu model tahmini değil, manuel review sonucudur.
    """
    counts: dict[str, int] = {}
    for utterance in transcript.utterances:
        counts[utterance.speaker_id] = counts.get(utterance.speaker_id, 0) + 1

    assignments = [
        SpeakerRoleAssignment(
            speaker_id=sid,
            role=DentistRole(expected["role"]),
            status=RoleStatus.CLEAR,
            utterance_count=counts.get(sid, 0),
            reason="Eval simülasyonu: hekim role review sonrası onayladı.",
        )
        for sid, expected in scenario["expected"].items()
    ]
    return RoleAssignmentResult(
        session_id=transcript.session_id,
        assignments=assignments,
        manual_review_required=False,
    )


def _fact_matches_expected(fact, expected: dict) -> bool:
    if fact.category != FactCategory(expected["category"]):
        return False
    if fact.source_role != DentistRole(expected["source_role"]):
        return False
    if fact.source_speaker != expected["source_speaker"]:
        return False
    if fact.tooth_number_fdi != expected["tooth_number_fdi"]:
        return False
    expected_status = expected["status"]
    if fact.status != (ProcedureStatus(expected_status) if expected_status else None):
        return False
    if fact.is_uncertain != expected["is_uncertain"]:
        return False
    return all(fragment in fact.source_quote for fragment in expected["quote_fragments"])


def _run_fact_assertions(report: dict, scenario: dict, transcript: SpeakerLabelledTranscript, llm: GeminiLLMProvider) -> None:
    expected_facts = scenario.get("expected_facts_after_role_approval")
    if expected_facts is None:
        report["matches"].append("facts/note: gate bloklu senaryoda extraction ve note generation çalıştırılmadı")
        return

    corrected = _dentist_approved_roles(scenario, transcript)
    role_labelled = stages.apply_dentist_role_correction(transcript, corrected)

    try:
        facts = stages.extract_clinical_facts(role_labelled, llm)
    except Exception as exc:  # noqa: BLE001 — eval raporu durmadan devam etsin
        report["error"] = f"facts {type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        return

    report["facts"] = facts
    for expected in expected_facts:
        if any(_fact_matches_expected(fact, expected) for fact in facts.facts):
            report["matches"].append(
                "fact: {category}/{role}/{speaker}/fdi={fdi}/status={status}/uncertain={uncertain}/quote~{quote}".format(
                    category=expected["category"],
                    role=expected["source_role"],
                    speaker=expected["source_speaker"],
                    fdi=expected["tooth_number_fdi"],
                    status=expected["status"],
                    uncertain=expected["is_uncertain"],
                    quote=" + ".join(expected["quote_fragments"]),
                )
            )
        else:
            report["mismatches"].append(f"expected fact bulunamadı: {expected!r}")

    uncertain_text = "\n".join(facts.uncertain_items)
    for fragment in scenario.get("expected_uncertain_fragments", []):
        if fragment.lower() in uncertain_text.lower():
            report["matches"].append(f"uncertain_items contains {fragment!r}")
        else:
            report["mismatches"].append(f"uncertain_items içinde beklenen parça yok: {fragment!r}")

    for violation in _fact_must_not_violations(scenario, facts):
        report["must_not_violations"].append(violation)

    _run_note_assertions(report, facts, llm)
    _run_procedure_assertions(report, scenario, facts)
    _run_code_suggestion_assertions(report, scenario, facts, llm)


def _run_note_assertions(report: dict, facts, llm: GeminiLLMProvider) -> None:
    try:
        note = stages.generate_clinical_note(facts, llm)
        stages._validate_note_against_facts(facts, note)
    except Exception as exc:  # noqa: BLE001 — eval raporu durmadan devam etsin
        report["error"] = f"note {type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        return

    section_counts = {
        "patient_complaint": len(note.patient_complaint),
        "history": len(note.history),
        "clinical_findings": len(note.clinical_findings),
        "assessment": len(note.assessment),
        "treatment_plan": len(note.treatment_plan),
        "procedures_note": len(note.procedures_note),
    }
    report["matches"].append(f"note: fact text/source_quote/source_role doğru bölümlere birebir taşındı {section_counts}")


def _run_procedure_assertions(report: dict, scenario: dict, facts) -> None:
    expected_procedures = scenario.get("expected_procedures_after_role_approval")
    if expected_procedures is None:
        return

    try:
        procedures = stages.extract_procedures(facts)
    except Exception as exc:  # noqa: BLE001 — eval raporu durmadan devam etsin
        report["error"] = f"procedures {type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        return

    if len(procedures) != len(expected_procedures):
        report["mismatches"].append(
            f"procedure sayısı: beklenen={len(expected_procedures)} gerçek={len(procedures)} "
            f"çıktı={[p.model_dump() for p in procedures]!r}"
        )

    for expected in expected_procedures:
        if any(_procedure_matches_expected(procedure, expected) for procedure in procedures):
            report["matches"].append(
                "procedure: {family}/fdi={fdi}/status={status}/surface={surface}/canal={canal}/quote~{quote}".format(
                    family=expected["procedure_family"],
                    fdi=expected["tooth_number_fdi"],
                    status=expected["status"],
                    surface=expected["surface_count"],
                    canal=expected["canal_count"],
                    quote=" + ".join(expected["quote_fragments"]),
                )
            )
        else:
            report["mismatches"].append(f"expected procedure bulunamadı: {expected!r}")


def _run_code_suggestion_assertions(report: dict, scenario: dict, facts, llm: GeminiLLMProvider) -> None:
    expected_bundles = scenario.get("expected_code_suggestions_after_role_approval")
    if expected_bundles is None:
        return

    procedures = stages.extract_procedures(facts)
    bundles = stages.match_codes_and_checklist(procedures, facts, llm)

    if len(bundles) != len(expected_bundles):
        report["mismatches"].append(
            f"code suggestion bundle sayısı: beklenen={len(expected_bundles)} gerçek={len(bundles)}"
        )

    for idx, expected in enumerate(expected_bundles):
        if idx >= len(bundles):
            report["mismatches"].append(f"expected code suggestion bundle eksik: index={idx} {expected!r}")
            continue
        bundle = bundles[idx]

        if len(bundle.candidates) == expected["candidate_count"]:
            report["matches"].append(f"code bundle {idx}: candidate_count == {expected['candidate_count']}")
        else:
            report["mismatches"].append(
                f"code bundle {idx} candidate_count: beklenen={expected['candidate_count']} gerçek={len(bundle.candidates)}"
            )

        candidate_codes = {candidate.code for candidate in bundle.candidates}
        explanation_codes = {explanation.code for explanation in bundle.explanations}
        if candidate_codes == explanation_codes:
            report["matches"].append(f"code bundle {idx}: explanations candidate code set ile birebir eşleşti")
        else:
            report["mismatches"].append(
                f"code bundle {idx}: explanation code set uyuşmadı "
                f"candidates={sorted(candidate_codes)} explanations={sorted(explanation_codes)}"
            )

        actual_states = {result.match_state for result in bundle.match_results}
        expected_states = {CodeMatchState(value) for value in expected["match_states"]}
        if actual_states == expected_states:
            report["matches"].append(
                f"code bundle {idx}: match_states == {[state.value for state in sorted(actual_states, key=lambda s: s.value)]}"
            )
        else:
            report["mismatches"].append(
                f"code bundle {idx} match_states: beklenen={[s.value for s in expected_states]} "
                f"gerçek={[s.value for s in actual_states]}"
            )

        first_result = bundle.match_results[0] if bundle.match_results else None
        if first_result is None:
            if expected["checklist"]:
                report["mismatches"].append(f"code bundle {idx}: checklist bekleniyordu ama match_result yok")
            continue

        checklist_by_id = {item.item_id: item for item in first_result.checklist}
        for item_id, expected_status in expected["checklist"].items():
            actual = checklist_by_id.get(item_id)
            if actual is None:
                report["mismatches"].append(f"code bundle {idx}: checklist item yok: {item_id}")
                continue
            if actual.status == ChecklistItemStatus(expected_status):
                report["matches"].append(f"code bundle {idx}: checklist {item_id} == {expected_status}")
            else:
                report["mismatches"].append(
                    f"code bundle {idx}: checklist {item_id}: beklenen={expected_status} gerçek={actual.status.value}"
                )


def _procedure_matches_expected(procedure, expected: dict) -> bool:
    if procedure.procedure_family != expected["procedure_family"]:
        return False
    if procedure.tooth_number_fdi != expected["tooth_number_fdi"]:
        return False
    if procedure.status != ProcedureStatus(expected["status"]):
        return False

    expected_surface = expected["surface_count"]
    if procedure.surface_count != (SurfaceCount(expected_surface) if expected_surface else None):
        return False

    expected_canal = expected["canal_count"]
    if procedure.canal_count != (CanalCount(expected_canal) if expected_canal else None):
        return False

    source_text = " ".join(procedure.source_quotes)
    return all(fragment in source_text for fragment in expected["quote_fragments"])


def _fact_must_not_violations(scenario: dict, facts) -> list[str]:
    checks = set(scenario.get("facts_must_not", []))
    violations: list[str] = []

    if "definite_infection" in checks:
        bad = [
            f
            for f in facts.facts
            if f.category in (FactCategory.CLINICAL_FINDINGS, FactCategory.ASSESSMENT)
            and ("iltihap var" in f.text.lower() or "enfeksiyon var" in f.text.lower() or "lezyon var" in f.text.lower())
            and not f.is_uncertain
        ]
        if bad:
            violations.append("definite_infection")

    if "patient_finding" in checks:
        if any(f.source_role == DentistRole.PATIENT and f.category == FactCategory.CLINICAL_FINDINGS for f in facts.facts):
            violations.append("patient_finding")

    if "drop_patient_infection_worry" in checks:
        if not any("iltihaplı mı" in f.source_quote for f in facts.facts):
            violations.append("drop_patient_infection_worry")

    if "temporary_restoration_decided" in checks:
        bad_statuses = {ProcedureStatus.PERFORMED, ProcedureStatus.PLANNED}
        if any(
            f.category == FactCategory.PROCEDURES
            and "geçici" in f.text.lower()
            and f.status in bad_statuses
            for f in facts.facts
        ):
            violations.append("temporary_restoration_decided")

    if "c_fact" in checks:
        if any(f.source_speaker == "C" for f in facts.facts):
            violations.append("c_fact")

    if "wrong_fdi_46" in checks:
        if any(f.tooth_number_fdi not in (None, 46) for f in facts.facts):
            violations.append("wrong_fdi_46")

    if "assign_mumbled_26" in checks:
        if any(f.tooth_number_fdi == 26 for f in facts.facts):
            violations.append("assign_mumbled_26")

    if "performed_not_preserved" in checks:
        if not any(f.category == FactCategory.PROCEDURES and f.status == ProcedureStatus.PERFORMED for f in facts.facts):
            violations.append("performed_not_preserved")

    if "patient_past_procedure_as_procedure" in checks:
        if any(f.source_role == DentistRole.PATIENT and f.category == FactCategory.PROCEDURES for f in facts.facts):
            violations.append("patient_past_procedure_as_procedure")

    if "assistant_assessment_or_plan" in checks:
        if any(
            f.source_role == DentistRole.ASSISTANT_OR_OTHER
            and f.category in (FactCategory.ASSESSMENT, FactCategory.TREATMENT_PLAN, FactCategory.CLINICAL_FINDINGS)
            for f in facts.facts
        ):
            violations.append("assistant_assessment_or_plan")

    if "extraction_planned" in checks:
        if any(
            f.category in (FactCategory.PROCEDURES, FactCategory.TREATMENT_PLAN)
            and ("çek" in f.text.lower() or "çek" in f.source_quote.lower())
            and "gündemde değil" not in f.source_quote.lower()
            and "düşünmüyoruz" not in f.source_quote.lower()
            for f in facts.facts
        ):
            violations.append("extraction_planned")

    if "s5_definite_rct" in checks:
        if any(
            f.category in (FactCategory.CLINICAL_FINDINGS, FactCategory.ASSESSMENT)
            and "kanal tedavisi" in f.text.lower()
            and ("gerekebilir" in f.source_quote.lower() or "kesin olarak söylemek zor" in f.source_quote.lower())
            and not f.is_uncertain
            for f in facts.facts
        ):
            violations.append("s5_definite_rct")

    if "s5_right_composite_current_procedure" in checks:
        if any(
            f.category == FactCategory.PROCEDURES
            and f.tooth_number_fdi == 16
            and ("kompozit" in f.text.lower() or "kompozit" in f.source_quote.lower())
            for f in facts.facts
        ):
            violations.append("s5_right_composite_current_procedure")

    if "s5_wrong_fdi" in checks:
        if any(f.tooth_number_fdi not in (None, 16, 27) for f in facts.facts):
            violations.append("s5_wrong_fdi")

    return violations


def run_scenario(scenario: dict, llm: GeminiLLMProvider) -> dict:
    """Bir senaryoyu gerçek modelle çalıştırır, rapor dict'i döner.

    Hata fırlatmaz — API hatası dahil her şey rapora `error` alanı olarak
    yazılır (eval script'in tamamı bir senaryo patladı diye durmamalı)."""
    name = scenario["name"]
    transcript = _t(scenario["session_id"], scenario["lines"])
    report: dict = {"name": name, "matches": [], "mismatches": [], "must_not_violations": [], "error": None}

    try:
        result = stages.assign_roles(transcript, llm)
    except Exception as exc:  # noqa: BLE001 — eval amaçlı, görünür şekilde raporla
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        return report

    by_speaker = {a.speaker_id: a for a in result.assignments}

    for sid, expected in scenario["expected"].items():
        actual = by_speaker.get(sid)
        if actual is None:
            report["mismatches"].append(f"speaker {sid} sonuçta yok (model konuşmacıyı atladı)")
            continue

        expected_role = DentistRole(expected["role"])
        if actual.role == expected_role:
            report["matches"].append(f"{sid}.role == {expected_role.value}")
        else:
            report["mismatches"].append(f"{sid}.role: beklenen={expected_role.value} gerçek={actual.role.value}")

        effective_status = _effective_expected_status(expected["status"], actual.utterance_count)
        if actual.status == effective_status:
            report["matches"].append(
                f"{sid}.status == {effective_status.value} (golden={expected['status']}, floor uygulandı: {effective_status != RoleStatus(expected['status'])})"
            )
        else:
            report["mismatches"].append(
                f"{sid}.status: beklenen(floor-uygulanmış)={effective_status.value} gerçek={actual.status.value} "
                f"(golden-set.md ham hedef={expected['status']}, utterance_count={actual.utterance_count})"
            )
        report.setdefault("reasons", {})[sid] = actual.reason  # insan/gevşek kontrol için

    if result.manual_review_required == scenario["expected_manual_review_required"]:
        report["matches"].append(f"manual_review_required == {scenario['expected_manual_review_required']}")
    else:
        report["mismatches"].append(
            f"manual_review_required: beklenen={scenario['expected_manual_review_required']} gerçek={result.manual_review_required}"
        )

    if result.requires_role_review == scenario["expect_gate_blocks"]:
        report["matches"].append(f"requires_role_review (gate bloke) == {scenario['expect_gate_blocks']}")
    else:
        report["mismatches"].append(
            f"requires_role_review: beklenen={scenario['expect_gate_blocks']} gerçek={result.requires_role_review}"
        )

    for check_name, check_fn in scenario["must_not"]:
        try:
            if not check_fn(by_speaker):
                report["must_not_violations"].append(check_name)
        except Exception as exc:  # eksik speaker vs. — violation olarak işaretle
            report["must_not_violations"].append(f"{check_name} (kontrol edilemedi: {exc})")

    _run_fact_assertions(report, scenario, transcript, llm)

    return report


def main() -> int:
    try:
        llm = GeminiLLMProvider()
    except RuntimeError as exc:
        print(f"DURDU: {exc}")
        return 2

    _debug_raw_call_s1(llm)

    reports = [run_scenario(s, llm) for s in SCENARIOS]

    print("=" * 70)
    any_failure = False
    for r in reports:
        print(f"\n--- {r['name']} ---")
        if r["error"]:
            print(f"  API/ÇALIŞMA HATASI: {r['error']}")
            any_failure = True
            continue
        for m in r["matches"]:
            print(f"  OK:  {m}")
        for m in r["mismatches"]:
            print(f"  MISMATCH: {m}")
            any_failure = True
        for v in r["must_not_violations"]:
            print(f"  *** MUST NOT İHLALİ (KRİTİK): {v}")
            any_failure = True
        if r.get("reasons"):
            print("  reason'lar (insan/gevşek kontrol — assert edilmedi):")
            for sid, reason in r["reasons"].items():
                print(f"    {sid}: {reason!r}")

    print("\n" + "=" * 70)
    if any_failure:
        print("SONUÇ: en az bir mismatch/ihlal var — golden-set.md'ye göre model "
              "çıktısı incelenmeli (bu bir CI gate'i değil, eval raporudur).")
        return 1
    print("SONUÇ: tüm senaryolar hedeflerle eşleşti.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
