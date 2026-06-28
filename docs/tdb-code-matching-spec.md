# TDB Code Matching + Documentation Checklist — V1 Spec

> Bu dosya, çıkarılmış `procedure` objesini TDB işlem koduna eşleştirme ve
> kod-bazlı dokümantasyon kontrolü (checklist) mantığını tanımlar.
> Repo'ya alınıp `CLAUDE.md`'den referanslanmak üzere yazılmıştır.

---

## 0. Kilit prensipler (değişmez)

1. **Kodu LLM uydurmaz.** Aday kodlar yalnızca kapalı, versiyonlanmış TDB
   veritabanından deterministik aramayla gelir. LLM sadece *açıklar* ve
   *belirsizlik işaretler*.
2. **Belirsizse tek kod seçilmez.** Yüzey sayısı / kanal sayısı / işlem durumu
   net değilse tüm adaylar gösterilir, `review_state = ambiguous` işaretlenir,
   hekim seçer.
3. **`required_documentation` veriden çekilmez.** Bu alanlar klinik uzmanlıkla
   (hekimlerle) yazılan tescilli içeriktir. Tek istisna: TDB "Dental İşlem
   Kodları ve Açıklamaları" kitapçığındaki **"rapor gerektirir"** bayrağı.
4. **Eksik dokümantasyon için önerilen ifade yalnızca transkriptten gelir.**
   Asla uydurulmaz. Transkriptte yoksa öneri yok — sadece "eksik" uyarısı.
5. **Sayısal confidence UI'da gösterilmez.** Yerine durum etiketi kullanılır.
6. **Son karar hekimde.** Tüm çıktı taslaktır.

---

## 1. Katman A — TDB Code Database (record şeması)

Her kod, sistemde şu yapıda saklanır. `code` ve `procedure_name` değerleri
**TDB 2026 Rehber Tarife / Dental İşlem Kodları ve Açıklamaları'ndan
doğrulanır** — aşağıdaki örneklerdeki kod numaraları placeholder'dır.

```json
{
  "code": "<TDB_2026'dan_doğrulanacak>",
  "procedure_name": "Kompozit Dolgu (İki Yüzlü)",
  "category": "Tedavi ve Endodonti",
  "source": "TDB 2026 Rehber Tarife",
  "source_version": "2026",
  "price": null,
  "vat": null,
  "report_required": false,
  "report_required_source": "TDB Dental İşlem Kodları ve Açıklamaları | null",
  "match_keys": {
    "procedure_family": "kompozit_dolgu",
    "surface_count": "two_surface",
    "canal_count": null,
    "tooth_region": null
  },
  "synonyms": ["iki yüzlü kompozit", "kompozit restorasyon", "sınıf 2 dolgu"],
  "required_documentation": [],          // bkz. Katman B
  "combination_rules": [],               // V2 (SUT/kombinasyon kuralları)
  "frequency_limit": null                // V2
}
```

> **Not:** `combination_rules` ve `frequency_limit` V1'de boş. Bu zenginlik
> SGK/SUT tarafında; V1 kapsamı dışı. Şema şimdiden açık ki sonra doldurulur.

---

## 2. Katman B — Checklist / required_documentation şeması

Bu, ürünün en değerli ve en zor kopyalanan parçası. Her `required_documentation`
maddesi şu yapıda:

```json
{
  "item_id": "tooth_number",
  "label": "Diş numarası (FDI)",
  "why": "İşlemin hangi dişe ait olduğu kayıtta zorunludur.",
  "expected_in": ["clinical_findings", "procedures", "treatment_plan"],
  "authored_by": "clinical_expert",          // clinical_expert | tdb_explanation
  "severity": "required"                      // required | recommended
}
```

`authored_by` alanı provenance içindir: maddenin kaynağı klinik uzmanlık mı,
yoksa TDB açıklama kitapçığı mı. Denetimde ve hekim onayında bu ayrım önemli.

### Checklist değerlendirme çıktısı (kod başına)

Her aday kod için, çıkarılmış fact'lere karşı her madde değerlendirilir:

```json
{
  "code": "<...>",
  "checklist": [
    {
      "item_id": "surface_name",
      "label": "Yüzey isimleri",
      "status": "missing",                    // found | review | missing
      "evidence_quote": null,                 // found ise transkript alıntısı
      "suggested_wording": null,              // YALNIZCA transkriptten; yoksa null
      "suggested_wording_source": null
    }
  ],
  "match_state": "insufficient_documentation"  // bkz. §4
}
```

**status kuralları:**
- `found` — gerekli bilgi fact'lerde net var. `evidence_quote` doldurulur.
- `review` — bilgi olabilir ama net değil / çelişik. Hekim kontrol etsin.
- `missing` — bulunamadı. Transkriptte ilgili ifade varsa `suggested_wording`
  o alıntıdan türetilir; yoksa `null` (uydurma yok).

---

## 3. Katman C — Eşleştirme pipeline'ı

```text
Extracted procedure object
        ↓
[1] Normalizasyon            (procedure_name → procedure_family, FDI doğrulama)
        ↓
[2] Deterministik DB araması (match_keys ile aday kodlar)
        ↓
[3] Aday kümesi             (0, 1 veya N aday)
        ↓
[4] Checklist değerlendirme  (her aday için required_documentation kontrolü)
        ↓
[5] LLM açıklama katmanı     (neden uyuyor + belirsizlik yorumu — KOD SEÇMEZ)
        ↓
[6] match_state ata
        ↓
Hekime sun → hekim seçer / düzeltir / onaylar
```

**Adım [1]–[4] deterministik koddur, LLM değil.** Adım [5] tek LLM çağrısıdır
ve yalnızca açıklama üretir.

### Eşleştirme dallanması

| Durum | Davranış | match_state |
|---|---|---|
| Tam tek aday + tüm zorunlu doküman var | Öner | `confirmed_by_documentation` |
| Tek aday ama zorunlu doküman eksik | Öner + eksikleri göster | `insufficient_documentation` |
| Birden çok aday (yüzey/kanal/durum belirsiz) | Hepsini göster, seçtirme | `ambiguous_multiple_candidates` |
| Hiç aday yok | Öneri yok, hekime bırak | `no_match` |

> `surface_count = "unclear"` → kompozit dolgu 1/2/3 yüzlü adaylarının hepsi
> döner, `ambiguous_multiple_candidates`. Sistem **tahmin etmez**.

---

## 4. match_state etiketleri (sayısal confidence yerine)

- `confirmed_by_documentation` — tek net aday, dokümantasyon tam.
- `needs_review` — aday net ama bir veya birden çok madde `review` durumunda.
- `insufficient_documentation` — aday net, zorunlu madde(ler) eksik.
- `ambiguous_multiple_candidates` — birden çok geçerli aday, hekim seçmeli.
- `no_match` — eşleşme yok.

UI bu etiketleri renk/metin olarak gösterir; **0.86 gibi sayı göstermez.**

---

## 5. LLM açıklama prompt'u (sadece açıklar, KOD SEÇMEZ)

```text
You are a Turkish dental coding explanation assistant.

You are given ONE extracted procedure object and a list of CANDIDATE TDB codes
that were already retrieved deterministically from a closed database.

Your job:
- Explain, in short Turkish, why each candidate code may fit the procedure.
- Point out what is ambiguous or missing.
- DO NOT invent codes. DO NOT pick a single code. DO NOT remove candidates.
- If surface count, canal count, or status is unclear, say so explicitly and
  state that the dentist must choose.

Hard rules:
1. Use only the candidate codes provided. Never output a code not in the list.
2. Never claim documentation exists if it is not in the extracted facts.
3. Keep epistemic uncertainty. Do not turn "gerekebilir/şüpheli" into certainty.
4. Output JSON only.

Input:
  procedure_object: {{procedure_object}}
  candidate_codes:  {{candidate_codes}}
  checklist_result: {{checklist_result}}

Output format:
{
  "explanations": [
    {
      "code": "<one of candidate_codes>",
      "fit_reason": "Kısa Türkçe açıklama.",
      "caveat": "Belirsizlik/eksik varsa; yoksa null"
    }
  ],
  "ambiguity_note": "Birden çok aday varsa neden, ve hekim neye karar vermeli",
  "dentist_must_choose": true
}
```

---

## 6. İlk 10 kod — worked entries

> Kod numaraları **placeholder**'dır; TDB 2026'dan doğrulanacak.
> `required_documentation` ilk taslaktır; hekim panelinde doğrulanıp kilitlenir.

### 6.1 Dişhekimi muayenesi
```json
{
  "procedure_family": "muayene",
  "required_documentation": [
    {"item_id": "chief_complaint", "label": "Başvuru şikayeti", "expected_in": ["patient_complaint"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "anamnesis", "label": "Anamnez", "expected_in": ["history"], "authored_by": "clinical_expert", "severity": "recommended"},
    {"item_id": "intraoral_finding", "label": "Ağız içi bulgu", "expected_in": ["clinical_findings"], "authored_by": "clinical_expert", "severity": "required"}
  ]
}
```

### 6.2 Periapikal röntgen
```json
{
  "procedure_family": "periapikal_rontgen",
  "required_documentation": [
    {"item_id": "tooth_or_region", "label": "Diş/bölge", "expected_in": ["procedures","clinical_findings"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "indication", "label": "Çekim gerekçesi (klinik endikasyon)", "expected_in": ["clinical_findings","assessment"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "radiographic_finding", "label": "Radyografik bulgu/yorum", "expected_in": ["clinical_findings"], "authored_by": "clinical_expert", "severity": "recommended"}
  ]
}
```

### 6.3 Panoramik film
```json
{
  "procedure_family": "panoramik_film",
  "required_documentation": [
    {"item_id": "indication", "label": "Çekim gerekçesi", "expected_in": ["assessment","clinical_findings"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "finding", "label": "Bulgu/yorum", "expected_in": ["clinical_findings"], "authored_by": "clinical_expert", "severity": "recommended"}
  ]
}
```

### 6.4 Kompozit dolgu — tek yüzlü
```json
{
  "procedure_family": "kompozit_dolgu",
  "surface_count": "one_surface",
  "required_documentation": [
    {"item_id": "tooth_number", "label": "Diş numarası (FDI)", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "surface_name", "label": "Yüzey ismi", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "indication", "label": "Gerekçe (çürük vb.)", "expected_in": ["clinical_findings"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "material", "label": "Kullanılan materyal", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "recommended"},
    {"item_id": "status", "label": "İşlem durumu (yapıldı/planlandı)", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"}
  ]
}
```

### 6.5 Kompozit dolgu — iki yüzlü
```json
{
  "procedure_family": "kompozit_dolgu",
  "surface_count": "two_surface",
  "required_documentation": [
    {"item_id": "tooth_number", "label": "Diş numarası (FDI)", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "surface_names", "label": "İki yüzeyin ismi (örn. mesio-okluzal)", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "indication", "label": "Gerekçe (çürük vb.)", "expected_in": ["clinical_findings"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "material", "label": "Kullanılan materyal", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "recommended"},
    {"item_id": "status", "label": "İşlem durumu", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"}
  ]
}
```
> Kritik: "iki yüzlü" demek yetmez; **hangi iki yüzey** dokümante edilmeli.
> Sadece `surface_count` varsa → `surface_names` = `missing`/`review`.

### 6.6 Kompozit dolgu — üç yüzlü
```json
{
  "procedure_family": "kompozit_dolgu",
  "surface_count": "three_surface",
  "required_documentation": [
    {"item_id": "tooth_number", "label": "Diş numarası (FDI)", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "surface_names", "label": "Üç yüzeyin ismi", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "indication", "label": "Gerekçe", "expected_in": ["clinical_findings"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "material", "label": "Materyal", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "recommended"},
    {"item_id": "status", "label": "İşlem durumu", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"}
  ]
}
```

### 6.7 Kanal tedavisi — tek kanal
```json
{
  "procedure_family": "kanal_tedavisi",
  "canal_count": "one_canal",
  "required_documentation": [
    {"item_id": "tooth_number", "label": "Diş numarası (FDI)", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "canal_count", "label": "Kanal sayısı", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "endo_diagnosis", "label": "Endodontik tanı/gerekçe (pulpa durumu, periapikal bulgu)", "expected_in": ["assessment","clinical_findings"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "radiograph", "label": "Röntgen bulgusu", "expected_in": ["clinical_findings"], "authored_by": "clinical_expert", "severity": "recommended"},
    {"item_id": "status", "label": "İşlem durumu", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"}
  ]
}
```

### 6.8 Kanal tedavisi — iki kanal
```json
{
  "procedure_family": "kanal_tedavisi",
  "canal_count": "two_canal",
  "required_documentation": [
    {"item_id": "tooth_number", "label": "Diş numarası (FDI)", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "canal_count", "label": "Kanal sayısı (2)", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "endo_diagnosis", "label": "Endodontik tanı/gerekçe", "expected_in": ["assessment","clinical_findings"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "radiograph", "label": "Röntgen bulgusu", "expected_in": ["clinical_findings"], "authored_by": "clinical_expert", "severity": "recommended"},
    {"item_id": "status", "label": "İşlem durumu", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"}
  ]
}
```
> Kanal sayısı belirsizse (`unclear`) → tek/iki/üç kanal adayları birlikte döner,
> `ambiguous_multiple_candidates`.

### 6.9 Diş çekimi
```json
{
  "procedure_family": "dis_cekimi",
  "required_documentation": [
    {"item_id": "tooth_number", "label": "Diş numarası (FDI)", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "indication", "label": "Çekim gerekçesi", "expected_in": ["assessment","clinical_findings"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "status", "label": "İşlem durumu", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"}
  ]
}
```

### 6.10 Detertraj (diş taşı temizliği)
```json
{
  "procedure_family": "detertraj",
  "required_documentation": [
    {"item_id": "indication", "label": "Gerekçe (diştaşı / gingival durum)", "expected_in": ["clinical_findings","assessment"], "authored_by": "clinical_expert", "severity": "required"},
    {"item_id": "region", "label": "Bölge (tüm ağız / çene / bölge)", "expected_in": ["procedures","clinical_findings"], "authored_by": "clinical_expert", "severity": "recommended"},
    {"item_id": "status", "label": "İşlem durumu", "expected_in": ["procedures"], "authored_by": "clinical_expert", "severity": "required"}
  ]
}
```

---

## 7. CLAUDE.md'ye gömülecek guardrail'lar

```text
- Kod yalnızca kapalı TDB DB'sinden gelir; LLM kod üretemez/değiştiremez.
- surface_count/canal_count/status "unclear" ise tek kod seçme → ambiguous.
- required_documentation "eksik" ise önerilen ifade yalnızca transkriptten;
  transkriptte yoksa öneri yok.
- match_state etiketle; sayısal confidence UI'da gösterme.
- required_documentation içeriği authored_by ile işaretli; çoğu clinical_expert,
  yalnız "rapor gerektirir" tdb_explanation kaynaklı.
- Tüm kod önerileri taslaktır; hekim seçer ve onaylar.
```
