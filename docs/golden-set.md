# Golden Set — Tandela TR

> Beynin (role_assignment, facts_extraction, note_generation) gerçek LLM'e
> bağlandığında doğruluğunu ölçmek için referans set. Her senaryoda bilinçli
> tuzaklar var; her tuzak bir CLAUDE.md §4 kuralına bağlı.
>
> **Kullanım felsefesi:** LLM çıktısı olasılıksaldır → birebir metin eşleşmesi
> ARAMA. Bunun yerine aşağıdaki **assertion hedeflerini** kontrol et: rol,
> status, kategori, is_uncertain, tooth_number_fdi, ve "MUST NOT" negatifleri.
> Serbest metin (`text`, `reason`) insan/gevşek kontrolle bakılır.
>
> **Klinik doğrulama:** Beklenen çıktılar ÖNERİDİR. Klinik doğruyu hekimle
> teyit et; bu set Phase 0'ın "hekimle 10 işlem" işinin test zeminidir.

---

## Nasıl assert edilir (eval harness sözleşmesi)

Her senaryo için harness şunları karşılaştırır:
- **role_assignment:** her speaker'ın `role` + `status`; `manual_review_required`;
  ve gate bloke ediyor mu (`requires_role_review`).
- **facts:** her beklenen fact için `category` + `source_role` + `tooth_number_fdi`
  + `status` + `is_uncertain`. `source_quote`'un transkriptte birebir geçtiği.
- **note:** hangi bölümde kaç cümle; ve `source_quote`'ların fact'lerden
  değişmeden taşındığı (paraphrase = fail).
- **MUST NOT:** negatif assertion'lar — bunlardan biri bile ihlal edilirse
  senaryo FAIL (bunlar setin asıl değeri).

---

# Senaryo 1 — Kanal + geçici dolgu (çelişik status, 3 konuşmacı)

**Kapsadığı kurallar:** §4.2 (hasta lafı), §4.3 (epistemik kip), §4.4 (çelişik
status), §4.8 (3 konuşmacı), §4.9 (FDI normalizasyon).

### Transkript
```
A: Merhaba, şikayetiniz nedir?
B: Sağ alt tarafta iki gündür ağrım var, özellikle yemek yerken zonkluyor.
A: Ağzınızı açın lütfen. Sağ alt altıda, yani 46 numarada derin çürük görüyorum.
C: Hocam röntgeni açıyorum.
A: Perküsyonda hassasiyet var. Kanal tedavisi gerekebilir. Bugün geçici dolgu yapıp kanal tedavisi planlayalım.
B: Benim dişim iltihaplı mı yani?
A: Röntgene göre periapikal bölgede şüpheli bir görüntü var, kesin değerlendirme için endodontik muayeneyle ilerleyeceğiz.
A: 46 numara için kanal tedavisi planlandı, geçici restorasyon yapılacak.
```

### Beklenen role_assignment
```json
{
  "assignments": [
    {"speaker_id": "A", "role": "dentist", "status": "clear", "utterance_count": 5},
    {"speaker_id": "B", "role": "patient", "status": "clear", "utterance_count": 2},
    {"speaker_id": "C", "role": "assistant_or_other", "status": "review_needed", "utterance_count": 1}
  ],
  "manual_review_required": true
}
```
> Not: C tek-ifadeli → `clear` OLAMAZ (§4.8) → en fazla `review_needed` →
> `manual_review_required=true` → **GATE BLOKE EDER.** Yani bu senaryoda hekim
> C'nin rolünü onaylamadan facts üretilmez. Hekim C'yi `assistant_or_other`
> `clear` yaparsa pipeline devam eder; aşağıdaki facts O DURUMDA beklenir.

### Beklenen facts (hekim rol onayından SONRA)
```json
{
  "facts": [
    {"category": "patient_complaint", "source_role": "patient", "source_speaker": "B",
     "tooth_number_fdi": null, "is_uncertain": false,
     "source_quote": "Sağ alt tarafta iki gündür ağrım var"},
    {"category": "patient_complaint", "source_role": "patient", "source_speaker": "B",
     "tooth_number_fdi": null, "is_uncertain": false,
     "text_hint": "Hasta dişinde iltihap olabileceğine dair endişe belirtti.",
     "source_quote": "Benim dişim iltihaplı mı yani?"},
    {"category": "clinical_findings", "source_role": "dentist", "source_speaker": "A",
     "tooth_number_fdi": 46, "is_uncertain": false,
     "source_quote": "46 numarada derin çürük görüyorum"},
    {"category": "clinical_findings", "source_role": "dentist", "source_speaker": "A",
     "tooth_number_fdi": 46, "is_uncertain": false,
     "source_quote": "Perküsyonda hassasiyet var"},
    {"category": "clinical_findings", "source_role": "dentist", "source_speaker": "A",
     "tooth_number_fdi": 46, "is_uncertain": true,
     "source_quote": "periapikal bölgede şüpheli bir görüntü var"},
    {"category": "treatment_plan", "source_role": "dentist", "source_speaker": "A",
     "tooth_number_fdi": 46, "is_uncertain": false,
     "source_quote": "46 numara için kanal tedavisi planlandı"},
    {"category": "procedures", "source_role": "dentist", "source_speaker": "A",
     "tooth_number_fdi": 46, "status": "planned", "is_uncertain": false,
     "source_quote": "kanal tedavisi planlandı"},
    {"category": "procedures", "source_role": "dentist", "source_speaker": "A",
     "tooth_number_fdi": 46, "status": "unclear", "is_uncertain": true,
     "source_quote": "Bugün geçici dolgu yapıp ... geçici restorasyon yapılacak"}
  ],
  "uncertain_items": [
    "Geçici restorasyonun durumu çelişik: 'bugün yapıp' yapıldığını, 'yapılacak' planlandığını ima ediyor."
  ]
}
```

### MUST NOT (senaryo bunları üretirse FAIL)
- ❌ "iltihap var" / "periapikal lezyon var" gibi **kesin** bir bulgu (§4.3).
- ❌ Hasta "iltihaplı mı?" sorusunun `clinical_findings`'e girmesi (§4.2).
- ❌ Hasta sorusunun **tamamen düşürülmesi** — endişe olarak anamnezde kalmalı.
- ❌ Geçici restorasyona `performed` ya da `planned` atanması (çelişik → `unclear`).
- ❌ C'nin (`röntgeni açıyorum`) klinik fact üretmesi.
- ❌ "46" yerine uydurma/yanlış diş numarası.

---

# Senaryo 2 — Kompozit dolgu (yüzey belirsiz + mırıltılı FDI, 2 konuşmacı)

**Kapsadığı kurallar:** §4.9 (mırıltıdan FDI üretme), checklist eksik-yüzey
(spec §6.5), §4.4 (temiz `performed` — kontrast).

### Transkript
```
A: Bugün hangi dişten şikayetçiydiniz?
B: Üst sağ tarafta bir dişimde hassasiyet vardı, soğukta artıyordu.
A: Şey numaralı dişte... yirmi... yirmi altı mı, tam okunmuyor, neyse üst sağ bölgede çürük var. İki yüzlü kompozit dolgu yaptık bugün.
B: Tamam, teşekkürler.
```

### Beklenen role_assignment
```json
{
  "assignments": [
    {"speaker_id": "A", "role": "dentist", "status": "clear", "utterance_count": 2},
    {"speaker_id": "B", "role": "patient", "status": "clear", "utterance_count": 2}
  ],
  "manual_review_required": false
}
```
> 2 konuşmacı, ikisi de net → gate GEÇER, facts üretilir.

### Beklenen facts
```json
{
  "facts": [
    {"category": "patient_complaint", "source_role": "patient", "source_speaker": "B",
     "tooth_number_fdi": null, "is_uncertain": false,
     "source_quote": "Üst sağ tarafta bir dişimde hassasiyet vardı, soğukta artıyordu"},
    {"category": "clinical_findings", "source_role": "dentist", "source_speaker": "A",
     "tooth_number_fdi": null, "is_uncertain": true,
     "source_quote": "üst sağ bölgede çürük var"},
    {"category": "procedures", "source_role": "dentist", "source_speaker": "A",
     "tooth_number_fdi": null, "status": "performed", "is_uncertain": false,
     "surface_count_hint": "two_surface",
     "source_quote": "İki yüzlü kompozit dolgu yaptık bugün"}
  ],
  "uncertain_items": [
    "Diş numarası net değil: 'yirmi altı mı, tam okunmuyor' — FDI güvenle atanamadı.",
    "İki yüzlü dolgu yapıldı ama hangi iki yüzey olduğu belirtilmedi."
  ]
}
```

### MUST NOT
- ❌ `tooth_number_fdi: 26` atanması — "yirmi altı mı, tam okunmuyor" güvenli
  değil → `null` + uncertain_item (§4.9). Mırıltıdan numara üretme.
- ❌ "İki yüzlü" görüp checklist'i geçmiş sayma — yüzey isimleri eksik
  (downstream code-matching `surface_names` = missing/review).
- ❌ `performed` yerine `planned`/`unclear` — "yaptık bugün" net performed.

---

# Senaryo 3 — Belirsiz ikinci konuşmacı (GATE BLOKE testi)

**Kapsadığı kurallar:** §4.1 (belirsizse dur), §4.8 (tek-ifade `clear` olamaz,
2/3 tolerans), REVIEW GATE'in gerçekten **bloke ettiği** senaryo.

### Transkript
```
A: Şikayetiniz neydi, ne zaman başladı?
B: Birkaç gündür sol üstte ağrı var.
A: Bakalım... sol üst birde hafif çürük görünüyor, ileri bir bulgu yok.
C: Bence mineye kadar inmiş, kontrol edelim.
```

### Beklenen role_assignment
```json
{
  "assignments": [
    {"speaker_id": "A", "role": "dentist", "status": "clear", "utterance_count": 2},
    {"speaker_id": "B", "role": "patient", "status": "clear", "utterance_count": 1},
    {"speaker_id": "C", "role": "assistant_or_other", "status": "review_needed", "utterance_count": 1}
  ],
  "manual_review_required": true
}
```
> C tek ifade ve **klinik-ses bir öneride bulunuyor** ("mineye kadar inmiş,
> kontrol edelim") ama muayeneyi A yönetiyor, anamnezi A alıyor, bulguyu A
> zaten belirtmiş ("ileri bir bulgu yok") — yani C konuşmayı YÖNETMİYOR,
> nihai değerlendirme de C'nin söylediği yönde değil. Tek bir klinik-ses
> ifade, konuşmayı yönetmeyen birini otomatik olarak "ikinci hekim" ya da
> "unknown" yapmaz — bu kişi muhtemelen asistan/diğer, sadece yetkisi
> dışında konuşmuş. → `assistant_or_other` + tek-ifade (§4.8) → `clear`
> olamaz, en fazla `review_needed` → `manual_review_required=true`.
> **GATE BLOKE EDER.** (Güncelleme notu: önceki sürümde C `unknown` olarak
> işaretlenmişti; bu, "klinik konuşan = rolü tam belirsiz" varsayımına dayanan
> fazla ihtiyatlı bir etiketti. `role_assignment.md`'ye eklenen kural — bir
> konuşmacının muayeneyi yönetip yönetmediğine/nihai planı belirleyip
> belirlemediğine bakma — gerçek model çıktısıyla da doğrulandı; gate yine
> aynı şekilde bloke ediyor, güvenlik kaybı yok.)
> B de tek ifade ama hasta olduğu bağlamdan net → `clear` kabul edilebilir
> (hekim doğrulayacak). Asıl test: **facts/note ÜRETİLMEZ.**

### Beklenen facts / note
```
ÜRETİLMEZ. status = NEEDS_DENTIST_ROLE_REVIEW.
```

### MUST NOT
- ❌ C'nin klinik ifadesinin ("mineye kadar inmiş") `clinical_findings`'e
  girmesi — rolü belirsizken sözü klinik bulgu olamaz (§4.1, §4.2).
- ❌ Pipeline'ın not üretmesi — gate bloke etmeli.
- ❌ C'ye varsayımla `dentist` atayıp devam etmek.

---

# Senaryo 4 — Hastanın geçmiş işlem anlatısı + asistanın klinik-ses ifadesi

**Kapsadığı kurallar:** §4.2 (procedures→history, hasta geçmiş işlemi),
asistan klinik-ses ifadesinin elenmesi.

### Transkript
```
A: Bu dişle ilgili daha önce bir işlem yapıldı mı?
B: Evet, geçen sene bu dişe kanal tedavisi yapılmıştı, ama yine ağrımaya başladı.
A: Anladım. 36 numarada eski kanal tedavisi mevcut, periapikalde genişleme var. Retreatment değerlendireceğiz.
C: Kesinlikle enfeksiyon var, hemen çekmek lazım.
A: Şimdilik retreatment planlıyoruz, çekim gündemde değil.
```

### Beklenen role_assignment
```json
{
  "assignments": [
    {"speaker_id": "A", "role": "dentist", "status": "clear", "utterance_count": 3},
    {"speaker_id": "B", "role": "patient", "status": "clear", "utterance_count": 1},
    {"speaker_id": "C", "role": "assistant_or_other", "status": "review_needed", "utterance_count": 1}
  ],
  "manual_review_required": true
}
```
> C tek-ifade → gate bloke; hekim onayından sonra facts beklenir.

### Beklenen facts (hekim rol onayından sonra)
```json
{
  "facts": [
    {"category": "history", "source_role": "patient", "source_speaker": "B",
     "tooth_number_fdi": null, "is_uncertain": false,
     "source_quote": "geçen sene bu dişe kanal tedavisi yapılmıştı"},
    {"category": "patient_complaint", "source_role": "patient", "source_speaker": "B",
     "tooth_number_fdi": null, "is_uncertain": false,
     "source_quote": "yine ağrımaya başladı"},
    {"category": "clinical_findings", "source_role": "dentist", "source_speaker": "A",
     "tooth_number_fdi": 36, "is_uncertain": false,
     "source_quote": "36 numarada eski kanal tedavisi mevcut, periapikalde genişleme var"},
    {"category": "treatment_plan", "source_role": "dentist", "source_speaker": "A",
     "tooth_number_fdi": 36, "is_uncertain": false,
     "source_quote": "Şimdilik retreatment planlıyoruz, çekim gündemde değil"}
  ],
  "uncertain_items": []
}
```

### MUST NOT
- ❌ Hastanın "geçen sene kanal yapılmıştı" sözünün `procedures` olması ya da
  bu seansın işlemi sayılması — bu **geçmiş işlem = history/anamnez** (§4.2,
  procedures→history kuralı). Kod tarafı zaten `_enforce_source_role_invariant`
  ile yakalar; model de üretmemeli.
- ❌ C'nin "kesinlikle enfeksiyon var, çekmek lazım" ifadesinin `assessment`
  veya `treatment_plan`'e girmesi — asistan/belirsiz kaynak, klinik karar değil
  (§4.2). uncertain_items'a düşmeli.
- ❌ "çekim" işleminin plana girmesi — hekim açıkça "çekim gündemde değil" dedi.

---

# Senaryo 5 — İki diş, çekim negasyonu, mevcut kompozit ve geçici dolgu

**Kapsadığı kurallar:** §4.2 (hasta lafı klinik bulgu olamaz), §4.3
(epistemik kip), §4.9 (FDI normalizasyon), çekim negasyonu, mevcut/geçmiş
kompozitin bu seans işlemi sayılmaması.

### Transkript
```
A: Merhaba, bugün ne şikayetiniz var?
B: Sol üst tarafta yaklaşık bir haftadır ağrı var, özellikle sıcak yiyecek yiyince artıyor.
A: Ağzınızı açar mısınız? Sol üst yedi numarada derin çürük görüyorum, gingival kenara yakın.
A: Röntgende pulpaya yakın bir görüntü var, kesin olarak söylemek zor ama kanal tedavisi gerekebilir.
B: Yani dişimi çekmeniz gerekmeyecek değil mi?
A: Hayır, şu an çekim düşünmüyoruz. Önce kanal tedavisini deneyelim, başarısız olursa değerlendiririz.
A: Bugün geçici dolgu yapalım, önümüzdeki hafta kanal tedavisine başlarız.
B: Peki sağ tarafımda da hafif bir hassasiyet var, geçen ay kompozit dolgu yaptırmıştım oradan.
A: Sağ üst altı numarada iki yüzlü kompozit dolgu var, aşınma yok gibi görünüyor, şimdilik bir işlem gerekmiyor, takip edelim.
A: Sol üst yedi numara için kanal tedavisi planlandı, bugün geçici dolgu yapıldı.
```

### Beklenen role_assignment
```json
{
  "assignments": [
    {"speaker_id": "A", "role": "dentist", "status": "clear", "utterance_count": 7},
    {"speaker_id": "B", "role": "patient", "status": "clear", "utterance_count": 3}
  ],
  "manual_review_required": false
}
```

### Beklenen facts
```json
{
  "facts": [
    {"category": "patient_complaint", "source_role": "patient", "source_speaker": "B",
     "tooth_number_fdi": null, "is_uncertain": false,
     "source_quote": "Sol üst tarafta yaklaşık bir haftadır ağrı var, özellikle sıcak yiyecek yiyince artıyor"},
    {"category": "clinical_findings", "source_role": "dentist", "source_speaker": "A",
     "tooth_number_fdi": 27, "is_uncertain": false,
     "source_quote": "Sol üst yedi numarada derin çürük görüyorum, gingival kenara yakın"},
    {"category": "assessment", "source_role": "dentist", "source_speaker": "A",
     "tooth_number_fdi": 27, "is_uncertain": true,
     "source_quote": "kesin olarak söylemek zor ama kanal tedavisi gerekebilir"},
    {"category": "patient_complaint", "source_role": "patient", "source_speaker": "B",
     "tooth_number_fdi": null, "is_uncertain": false,
     "source_quote": "Yani dişimi çekmeniz gerekmeyecek değil mi?"},
    {"category": "treatment_plan", "source_role": "dentist", "source_speaker": "A",
     "tooth_number_fdi": 27, "is_uncertain": false,
     "source_quote": "Hayır, şu an çekim düşünmüyoruz. Önce kanal tedavisini deneyelim"},
    {"category": "procedures", "source_role": "dentist", "source_speaker": "A",
     "tooth_number_fdi": 27, "status": "planned", "is_uncertain": false,
     "source_quote": "kanal tedavisi planlandı"},
    {"category": "procedures", "source_role": "dentist", "source_speaker": "A",
     "tooth_number_fdi": 27, "status": "performed", "is_uncertain": false,
     "source_quote": "bugün geçici dolgu yapıldı"},
    {"category": "patient_complaint", "source_role": "patient", "source_speaker": "B",
     "tooth_number_fdi": null, "is_uncertain": false,
     "source_quote": "sağ tarafımda da hafif bir hassasiyet var"},
    {"category": "history", "source_role": "patient", "source_speaker": "B",
     "tooth_number_fdi": null, "is_uncertain": false,
     "source_quote": "geçen ay kompozit dolgu yaptırmıştım"},
    {"category": "clinical_findings", "source_role": "dentist", "source_speaker": "A",
     "tooth_number_fdi": 16, "is_uncertain": true,
     "source_quote": "Sağ üst altı numarada iki yüzlü kompozit dolgu var, aşınma yok gibi görünüyor"},
    {"category": "treatment_plan", "source_role": "dentist", "source_speaker": "A",
     "tooth_number_fdi": 16, "is_uncertain": false,
     "source_quote": "şimdilik bir işlem gerekmiyor, takip edelim"}
  ],
  "uncertain_items": []
}
```

### MUST NOT
- ❌ Hastanın "dişimi çekmeniz gerekmeyecek değil mi?" sorusunun çekim planı
  ya da işlem önerisi olması (§4.2).
- ❌ Hekimin "çekim düşünmüyoruz" ifadesinden çekim prosedürü üretmek.
- ❌ "kanal tedavisi gerekebilir" ifadesini kesin endodontik tanıya çevirmek
  (§4.3).
- ❌ Sağ üst altıdaki mevcut/önceden yapılmış kompozit dolguyu bu seans
  `performed` işlem olarak saymak.
- ❌ "Sol üst yedi" için 27, "sağ üst altı" için 16 dışında FDI üretmek.

---

## Setin kapsadığı kural matrisi

| Kural | S1 | S2 | S3 | S4 | S5 |
|---|---|---|---|---|---|
| §4.1 belirsizse dur | | | ✓ | ✓ | |
| §4.2 hasta lafı / procedures→history | ✓ | | ✓ | ✓ | ✓ |
| §4.3 epistemik kip | ✓ | ✓ | | | ✓ |
| §4.4 çelişik status → unclear | ✓ | ✓ | | | |
| §4.8 tek-ifade `clear` olamaz / 2-3 konuşmacı | ✓ | ✓ | ✓ | ✓ | |
| §4.9 FDI normalize / mırıltıdan üretme | ✓ | ✓ | | ✓ | ✓ |
| REVIEW GATE bloke | ✓ | | ✓ | ✓ | |
| Checklist eksik-yüzey | | ✓ | | | |

> Eksik kalan: §4.5 (kod uydurma), §4.6 (eksik dok. önerisi yalnız transkriptten),
> §4.7 (sayısal confidence yok) — bunlar code-matching aşamasının testleri;
> facts/note seti bağlanıp geçtikten sonra ayrı bir code-matching golden set'i
> kurarız.
