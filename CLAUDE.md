# CLAUDE.md — Klinia TR (AI Dental Documentation Assistant)

> Bu dosya projenin **gerçeğin tek kaynağıdır**. Claude Code her oturumda okur.
> Buradaki güvenlik kuralları (§4) pazarlık konusu değildir; hiçbir görev bunları
> çiğnemez. Bir kural yanlış uygulanırsa, düzeltip bu dosyaya yeni satır ekle.

---

## 1. Ürün özeti

Türkçe çalışan, hekim-hasta görüşmesini klinik not taslağına çeviren, TDB işlem
kodu öneren ve **hekim onayıyla** export edilen web tabanlı dokümantasyon asistanı.

**Çekirdek prensip:** AI karar vermez, taslak üretir. Hekim kontrol eder,
düzeltir, onaylar. Ürün teşhis koymaz, tedavi önermez, otomatik kayıt yapmaz.

---

## 2. Teknik stack (kilitli)

- **Frontend:** Next.js / React, Tailwind
- **Backend:** FastAPI (Python) — AI/audio pipeline, NLP, self-host geçişi için
- **DB:** PostgreSQL
- **Async:** Redis + Celery (RQ'ya geçiş açık; bkz §10)
- **Repo:** tek repo, `frontend/` ve `backend/` ayrı klasör (mikroservis değil)

---

## 3. V1 pipeline (batch)

```
Audio capture → audio preprocessing → ASR (+word timestamps) → diarization
→ alignment → role assignment → [REVIEW GATE] → clinical facts extraction
→ clinical note generation → procedure extraction → TDB code matching + checklist
→ hekim review/edit/approve → export/copy
```

- **Batch**, real-time değil (V1). Ses kaydedilir, seans sonu işlenir.
- **REVIEW GATE:** rol ataması `unresolved`/`unknown`/`review_needed` ya da
  `manual_review_required=true` ise pipeline **durur**; not üretmeden önce hekimden
  rol düzeltmesi ister. Bu kod seviyesinde orchestration kuralıdır (bkz. §4.8).

### Beyin (LLM katmanı)
Üç aşama, prompt dosyaları `backend/app/prompts/`:
1. `role_assignment` — Speaker A/B/C → dentist/patient/assistant_or_other/unknown
2. `clinical_facts_extraction` — transkriptten **kanıtlı** fact + provenance
3. `clinical_note_generation` — yalnızca fact JSON'undan taslak (yeni bilgi yok)

Aşama 2→3 arası kontrat: fact metnini **yeniden yazma, taşı**; her cümlede
`source_quote` baştan sona korunur.

### Kod eşleştirme + checklist
Detaylı şema: `docs/tdb-code-matching-spec.md`. Özet: deterministik DB araması →
aday kodlar → checklist değerlendirme → LLM **yalnızca açıklar** (kod seçmez/
uydurmaz) → hekim seçer.

---

## 4. GÜVENLİK KURALLARI (değişmez)

1. **Belirsizse tahmin etme.** Status/yüzey/kanal/rol net değilse `unclear`/
   `unknown` döndür, hekime sor. Asla varsayılan değer uydurma.
2. **Hasta lafı klinik bulgu olamaz.** Hasta ifadesi yalnızca
   `patient_complaint`/`history`'ye gider. Hekim açıkça doğrulamadıkça klinik
   bulgu/tanı yapılmaz. (Örn. hasta "iltihaplı mı?" → not "iltihap var" yazamaz;
   gerekirse anamnezde "hasta endişe belirtti" olarak yer alır, **silinmez**.)
3. **Epistemik belirsizliği koru.** "şüpheli/gerekebilir/olabilir" kesinliğe
   dönüştürülmez.
4. **Status çelişikse `unclear`.** "Bugün yapıp...yapılacak" gibi çelişen ifade
   `planned` diye tahmin edilmez; `unclear` + `uncertain_items`.
5. **Kodu LLM üretmez.** Aday kodlar yalnızca kapalı/versiyonlanmış TDB DB'sinden
   gelir. LLM listeden kod ekleyemez/çıkaramaz/tek kod seçemez.
6. **Eksik dokümantasyon önerisi yalnızca transkriptten.** Transkriptte yoksa
   öneri yok — sadece "eksik" uyarısı. Asla uydurma ifade.
7. **Sayısal confidence UI'da gösterilmez.** Yerine durum etiketi:
   `clear/review_needed/unresolved` (rol), `found/review/missing` (checklist),
   `confirmed_by_documentation/needs_review/insufficient_documentation/
   ambiguous_multiple_candidates/no_match` (kod).
8. **Tek-ifadeli konuşmacı `clear` olamaz.** Az utterance → en fazla
   `review_needed`. Konuşmacı sayısı 2–3 toleranslı.
   - `review_needed` bir konuşmacı da REVIEW GATE'i bloke eder (unresolved/unknown
     gibi). `review_needed` belirsizliktir; §4.1 gereği belirsizse durup hekime
     sorulur, tahmin edilmez.
9. **FDI doğrula.** Diş no normalize edilir ("sağ alt altı"→46) ve geçerli
   aralıkta mı (11–48, geçerli çeyrek) kontrol edilir. Mırıltıdan numara üretilmez.
10. **Her şey taslaktır.** Hiçbir not/kod hekim onayı olmadan klinik geçerli
    sayılmaz. Onay ve export her zaman lisanslı hekimde.

---

## 5. KVKK / veri kuralları

- **Ses kalıcı saklanmaz.** Pipeline biter bitmez ham ses **otomatik silinir**
  (hedef: dakikalar içinde; retry için sert üst sınır §10).
- Tüm veri ve **geçici işleme** AB/Türkiye uygun bölgede. ABD'ye veri gitmez.
- Sağlayıcılarla DPA; ses/metin **model eğitimi için kullanılmaz** (sözleşmede).
- Hasta verisi minimum: MVP'de hasta adı zorunlu değil; anonim session / opsiyonel
  baş harf.
- Klinik bazlı veri izolasyonu + role-based access control.
- Audit log: kim, neyi, ne zaman; değişiklik kaynağı `ai`/`voice`/`manual`.

---

## 6. Provider soyutlaması (kilitli)

ASR/diarization backend'e doğrudan gömülmez. Adapter arkasında:

```python
class AudioProcessingProvider:
    def transcribe(audio) -> Transcript          # word-level timestamps
    def diarize(audio) -> SpeakerSegments
    def align(transcript, diarization) -> SpeakerLabelledTranscript
```

V1: AB-region'lı entegre bulut API (tek çağrıda transcribe+diarize). İleride
self-host WhisperX + pyannote aynı arabirimle takılır. **Vendor seçimi §10'da TBD.**

LLM çağrıları da aynı veri kısıtlarına (AB/DPA/no-training) tabidir.

---

## 7. Veri modeli (özet)

`clinics, users, patients, sessions, transcripts, clinical_notes,
procedure_codes, code_suggestions, documentation_checks, audit_logs`.
Tam şema: `docs/data-model.md` (henüz yazılmadı).

---

## 8. Repo yapısı (hedef)

```
frontend/         Next.js
backend/
  app/
    api/          FastAPI routes
    pipeline/     audio→note orchestration (REVIEW GATE burada)
    providers/    AudioProcessingProvider adapters
    prompts/      role_assignment / facts_extraction / note_generation
    tdb/          code DB, matching, checklist
    models/       SQLAlchemy
    workers/      Celery tasks
docs/             spec'ler (tdb-code-matching-spec.md, data-model.md ...)
```

---

## 9. Scope

**V1:** Clinical Notes + Procedure Codes + Documentation Review + Approve/Export.
**V1 dışı (V2+):** Perio charting, voice editing, real-time, SGK/SUT kombinasyon
& frekans kuralları, WhatsApp/hasta mesajı, röntgen/AI teşhis, otomatik fatura.

`required_documentation` içeriği **tescilli klinik IP**; veriden çekilmez,
hekimlerle yazılıp panelde kilitlenir (`authored_by` ile işaretli).

### Kod sistemi / Medula / entegrasyon (netleşen kararlar)

- **Kod kaynağı AÇIK KARAR, segmente bağlı.** Gözlemlenen hastane (Medipol
  HSYS) SUT kodları kullanıyor (örn. P403306, 404220), TDB Rehber Tarife
  değil — özel hastane bile Medula'ya SUT'la kodlar. Küçük özel klinik
  (SGK'sız) TDB kullanabilir. Hedef segment kararı V1 kod kaynağını belirler;
  kod DB zaten soyut → kaynak (TDB/SUT) parametrik tutulmalı, koda
  gömülmemeli.
- **Medula konumlanması.** Ürün Medula'ya DOĞRUDAN bağlanmaz (SGK
  yetkilendirmesi + mevcut HBYS işi gerekir). Değer = Medula'ya gidecek doğru
  SUT kodunu hekim adına hazırlamak; gönderimi klinik kendi HBYS'siyle yapar.
  Bu, kod kaynağının SUT olmasını güçlü biçimde işaret eder.
- **Entegrasyon kademeleri.** V1 = copy/export (üçüncü-taraf izni
  gerektirmez, bağımsız değer). Doğrudan HSYS/Medula entegrasyonu V2+ —
  kurum + sistem sağlayıcı + olası Bakanlık iznine bağlı. Çekirdek değer
  entegrasyona BAĞIMLI olmamalı.
- **Export hedefi (HSYS-tarzı, gözlemlendi).** İşlemler diş FDI'ye göre
  gruplu; her işlemde Planlayan Doktor+Tarih ile Uygulayan Doktor+Uygulama
  Tarihi AYRI tutulur. `ProcedureObject`'e planlama/uygulama ayrımı V2'de
  eklenmeli (henüz yok).
- **Çok-seans (V1).** Seanslar `patient_id` altında kronolojik ama
  BAĞIMSIZ. Yeni seans önceki seansları fact kaynağı olarak KULLANMAZ.
  Seanslar-arası bağlam V2 kapsamına bırakıldı; geldiğinde yalnızca
  `APPROVED` notlar, yalnızca hekime REFERANS olarak gösterilecek — fact
  kaynağı olarak değil. O zaman provenance + §4.2 ("hasta lafı klinik bulgu
  olamaz") buna göre genişletilmeli.

---

## 10. Benim adına seçtiğim varsayılanlar — DEĞİŞTİREBİLİRSİN

> Bunları sen onaylamadan "kilitli" sayma:

- **Async:** Celery seçtim (RQ yerine) — daha olgun. İstersen RQ'ya çevir.
- **Ses retention sert sınırı:** retry için **60 dk** öneriyorum, sonra zorunlu
  silme. Daha kısa istersen söyle.
- **ASR vendor:** somut vendor **TBD**. Kısıtlar kilitli (AB-region, DPA,
  no-training, retention kapalı), adapter hazır. Vendor shootout'u build'in
  başında yaparsın.
- **Repo:** tek repo / iki klasör seçtim. Ayrı repo istersen değişir.
- **LLM modeli:** beyin için somut model seçmedim; §6 kısıtlarına uyan herhangi
  biri. Karar senin.

---

## 11. Çalışma kuralı

Bir şeyi yanlış yaptığımda düzelt ve **bu dosyaya kural ekle** ki tekrarlanmasın.
Dosyayı kısa tut; büyük detay `docs/` altındaki ayrı dosyalara gider.

---

## 12. Devir notu (Codex'e devam için)

- `role_assignment` GERÇEK Gemini (`gemini-3.5-flash`) ile doğrulandı;
  golden-set'in 4 senaryosu da (role katmanı) yeşil (bkz.
  `backend/evals/eval_golden_roles.py`, `docs/golden-set.md`).
- Prompt'taki ("`backend/app/prompts/role_assignment.md`") üst seviye çıktı
  anahtarı yanlışlıkla "speakers" idi, "assignments" olarak düzeltildi
  (`RoleAssignmentResult` tipiyle hizalı). Parse katmanına (`stages.py`)
  savunma olarak alias fallback eklendi: model yine "speakers" dönerse de
  kabul edilir; ikisi de yoksa hâlâ fail-safe'e düşer (§4.1 — değişmedi).
- **SIRADAKİ ADIM:** `clinical_facts_extraction` prompt'unu `stages.py`'a
  bağla, eval'e facts assertion'larını ekle, golden-set'e karşı çalıştır.
  Sonra `clinical_note_generation`.
- **DOĞRULAMA YÖNTEMİ (`role_assignment`'ta izlenen, tekrar kullanılacak):**
  prompt yaz → stage'e bağla → golden-set'e karşı GERÇEK modelle eval →
  mismatch incele → ya prompt'u ya golden-set'i düzelt.
- Gemini eval'i (`eval_golden_roles.py`) yalnızca kendi makinende çalışır —
  Cowork sandbox'ı Gemini API domain'ini proxy seviyesinde engelliyor
  (`httpx.ProxyError: 403 Forbidden`, kod/key hatası değil). Repo clone
  sonrası `backend/.env`'i `.env.example`'dan elle yeniden kurman gerekir
  (gitignore'da, commit edilmez).
