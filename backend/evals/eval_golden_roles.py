"""
eval_golden_roles.py — docs/golden-set.md'nin 4 senaryosunu GERÇEK Gemini ile
çalıştırır (role_assignment katmanı).

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
manual_review_required/requires_role_review hedefleri ve MUST NOT
negatifleri kontrol edilir; `reason` gibi serbest metin alanları insan/gevşek
kontrol için ekrana basılır, assert edilmez.

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
from app.pipeline.types import DentistRole, RoleStatus, SpeakerLabelledTranscript, Utterance
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
