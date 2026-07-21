# Klinia TR MVP roadmap

Bu dosya projenin ürün/MVP ilerleme planıdır. `AGENTS.md` güvenlik kuralları
ve `docs/product-lines.md` ürün tanımları bu dosyaya göre uygulanır.

## Mevcut durum

### Bitti / doğrulandı

- Mimari ve güvenlik kafesi:
  - `AGENTS.md`,
  - review gate,
  - provenance,
  - source-role invariant,
  - sayısal confidence göstermeme kuralı.
- `role_assignment` gerçek Gemini ile golden-set eval içinde doğrulandı.
- `clinical_facts_extraction` ve `clinical_note_generation` gerçek LLM çağrısına
  bağlı; parse fail-safe ve provenance kontrolleri var.
- Procedure extraction ve fixture code matching/checklist çalışıyor.
- Gerçek ses demo hattı var:
  - tarayıcı MediaRecorder kaydı,
  - Gemini audio provider,
  - speaker-labelled transcript,
  - ham sesin işlem sonrası silinmesi.
- Demo UI var:
  - Hasta görüşmesi,
  - role review,
  - clinical note review,
  - procedure/code checklist,
  - approve/export,
  - Perio dikte demo slice.
- MVP persistence demo katmanı var:
  - SQLAlchemy models,
  - Alembic migration,
  - local SQLite / configurable `DATABASE_URL`,
  - transcripts/notes/review/export/audit records.

### Yazıldı ama daha güçlendirilmeli

- `clinical_facts_extraction` ve `clinical_note_generation` gerçek modelle bağlı,
  ancak golden-set facts/note eval raporları ayrı dosyalara bölünüp düzenli
  çalıştırılmalı.
- Perio dikte parser frontend demo katmanında; backend stage ve eval sözleşmesi
  haline taşınmalı.
- Audio provider Gemini demo için çalışıyor; üretim ASR/diarization vendor kararı
  hâlâ açık.

### Kritik eksikler

- Production PostgreSQL + Redis/Celery kurulumu.
- Tam code-source DB:
  - SUT/TDB seçimi,
  - versioned code records,
  - klinik uzman tarafından doğrulanmış `required_documentation`.
- Production auth/RBAC ve klinik veri izolasyonu.
- Voice editing / düzeltme komutları.
- Tam gerçek zamanlı perio charting.
- Deployment/hardening:
  - secrets management,
  - region/DPA/no-training doğrulamaları,
  - retention watchdog,
  - backup/encryption politikaları.

## MVP kapsamı

### Uçtan uca çalışacak MVP

- Clinical Notes:
  - ses,
  - Türkçe klinik not taslağı,
  - hekim review/onay.
- Procedure Codes + Documentation Review:
  - not/procedure objesi,
  - aday kod,
  - checklist,
  - hekim seçimi.
- Approve & Export:
  - onaylı not/kod,
  - copy/export payload.

### Demo slice

- Perio dikte:
  - kayıt sonrası yapılandırılmış periodontal chart taslağı,
  - gerçek zamanlı değil.

### V2+

- Gerçek zamanlı perio charting.
- Voice editing.
- Doğrudan HSYS/Medula entegrasyonu.
- SGK/SUT kombinasyon ve frekans kuralları.
- Çok-seans bağlamı.
- Production RBAC ayrıntıları.

## Kritik yol

Ses girişi → beyin → kalıcılık → hekim review UI → export.

Bu zincirin her halkası olmadan çalışan MVP yoktur. Faz sırası bu nedenle
önemlidir.

## Bloklayan açık kararlar

### ASR / diarization vendor

MVP demo için Gemini audio provider bağlıdır. Production için entegre ASR +
diarization provider seçimi hâlâ açık:

- AB/Türkiye uygun bölge,
- DPA,
- no-training,
- retention kapalı veya sözleşmeyle sınırlı.

Gerçek hasta verisi vendor shootout/demo ortamına gönderilmez.

### Kod sistemi

Kod kaynağı hedef segmente bağlıdır:

- Hastane / Medula hedefi: SUT.
- Küçük özel klinik / SGK dışı hedef: TDB.

Karar verilene kadar kod DB soyut ve kaynak-parametrik tutulur.

## Fazlar

### Faz A - Beyni doğrula

Amaç: Role assignment sonrası facts ve note aşamalarının gerçek modelde güvenlik
kurallarına uyduğunu kanıtlamak.

Durum:

- Role assignment golden-set yeşil.
- Facts/note gerçek LLM çağrısına bağlı.
- Eval kodu genişletildi ama ayrı, okunabilir eval dosyalarına bölünmeli.

Sonraki iş:

- `eval_golden_facts.py` ve `eval_golden_notes.py` dosyalarını ayır.
- Golden-set "beklenen facts" için:
  - category,
  - source_role,
  - tooth_number_fdi,
  - status,
  - is_uncertain,
  - "must not" negatiflerini assert et.
- Birebir fact text arama; `source_quote` transkriptte geçmeli.
- Gate'te bloke senaryolar için hekim rol onayı simülasyonu kullan.
- CI'a koyma; gerçek Gemini ile lokal çalıştır.

Doğrulama:

```bash
cd backend
python3 -m evals.eval_golden_facts
python3 -m evals.eval_golden_notes
```

### Faz B - Ses girişi

Amaç: Ürünü metin işleyiciden gerçek ses tabanlı asistan haline getirmek.

Durum:

- Tarayıcı MediaRecorder akışı var.
- Gemini audio demo provider var.
- `AudioProcessingProvider` adapter soyutlaması var.
- Ham ses işlem sonrası siliniyor.

Sonraki iş:

- Production ASR/diarization vendor kararını ver.
- Seçilen vendor için provider implementasyonu ekle.
- Uzun kayıt, hata, retry ve timeout durumlarını kalıcı job modeliyle bağla.

Doğrulama:

- Simüle diş seansı sesi → speaker-labelled transcript → role gate →
  note/code review.

### Faz C - Kalıcılık

Amaç: Seansların kapanıp tekrar açılabildiği kalıcı MVP.

Durum:

- SQLAlchemy model ve migration var.
- Local SQLite / `DATABASE_URL` ile çalışıyor.
- Session, transcript, note, approval, export, audit kayıtları var.

Sonraki iş:

- Docker Compose ile PostgreSQL + Redis ekle.
- `clinics`, `users`, `patients`, `procedure_codes`, `code_suggestions`,
  `documentation_checks` tablolarını production modeline genişlet.
- Ses retention watchdog ekle:
  - hedef dakikalar içinde silme,
  - sert üst sınır 60 dakika.

Doğrulama:

- Bir seans işlenip kaydedilir.
- Server restart sonrası seans açılır.
- Ham ses diskte kalmaz.
- Audit log dolar.

### Faz D - Hekim arayüzü

Amaç: Hekimin baştan sona kayıt, review, düzeltme, onay ve export yapabilmesi.

Durum:

- Tek ekran demo workspace var.
- Recording, transcript, role review, note review, code checklist, approve/export
  yüzeyleri var.

Sonraki iş:

- Dashboard:
  - session listesi,
  - draft/approved durumları,
  - yeni session.
- Note Review:
  - cümle bazlı source quote UI kalıcı ve düzenlenebilir olsun.
- Code Review:
  - gerçek kod DB ile adaylar,
  - `found/review/missing` checklist,
  - match state etiketleri.
- Approve & Export:
  - TXT/PDF/copy hedefleri.

Doğrulama:

- Hekim UI üzerinden kayıt alır, gate'te rol onaylar, notu düzeltir, kod seçer,
  onaylar ve export eder.

### Faz E - Kod DB + checklist

Amaç: Kod önerisini fixture'dan gerçek veriye geçirmek.

Blokaj:

- SUT/TDB kararına bağlıdır.

Sonraki iş:

- İlk yaklaşık 10 işlem için kapalı, versioned code DB seed et.
- Kodlar gerçek kaynaktan doğrulansın; uydurulmasın.
- `required_documentation` taslakları `authored_by: clinical_expert` ve
  `status: unverified` olarak işaretlensin.
- Hekimlerle oturup gereksinimler doğrulanıp kilitlensin.
- LLM yalnızca açıklama yapar; kod seçmez.

Doğrulama:

- Gerçek not → doğru aday kodlar + eksik dokümantasyon uyarısı.
- Belirsiz durumda tek kod seçilmez; hekim seçer.

### Faz F - MVP cila

Amaç: Bir sahte hasta senaryosunu başkasına gösterilebilir hale getirmek.

Durum:

- Basit dev auth header'ları var.
- Perio dikte demo slice var.
- Tek komut demo script'i var.

Sonraki iş:

- Production-lite auth + klinik veri izolasyonu.
- Boş/hata/yükleme durumlarını parlat.
- "Taslak" etiketi her çıktıda görünür olsun.
- 2-3 sahte seans smoke test senaryosu yaz.

Doğrulama:

- Sahte hasta demo senaryosu baştan sona akıcı çalışır.

## Her fazda değişmez

- `AGENTS.md` §4 güvenlik kuralları çiğnenmez.
- Review gate klinik nottan önce çalışır.
- Provenance (`source_role` + `source_quote`) düşmez.
- Belirsizse tahmin edilmez; `unclear/unknown/review_needed` ile hekime sorulur.
- Her yeni LLM bağlamada:
  - prompt,
  - golden-set gerçek model eval,
  - mismatch inceleme,
  - prompt/golden-set düzeltme.
- Her faz sonunda:
  - değişiklikleri gözden geçir,
  - testleri çalıştır,
  - commit + push yap.
- Yanlış davranış görülürse `AGENTS.md` veya ilgili `docs/` dosyasına kural ekle.
