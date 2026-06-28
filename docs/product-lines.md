# Tandela TR product lines

Bu dosya ürün kapsamı için kaynak dokümandır. Uygulama yeni ürün üretmez;
aşağıdaki tanımlı iki ürün hattını geliştirir.

## 1. Hasta toplantısı: Klinik notlar + işlem kodları

### Amaç

Hekim hasta ile her zamanki gibi konuşur. Tandela arka planda görüşmeyi kaydeder,
hekim/hasta/asistan konuşmacılarını ayırır ve hekim incelemesi için klinik not
taslağı üretir.

### Çıktılar

- Konuşmacı etiketli transkript.
- Klinik not taslağı:
  - hasta şikayeti,
  - öykü,
  - klinik durum/bulgular,
  - hekim değerlendirmesi,
  - tedavi planı,
  - prosedür/not bölümleri.
- İşlem/procedure nesneleri.
- Kod adayları ve kod başına dokümantasyon checklist'i.
- Hekim review/edit/approve sonrası export/copy payload.

### Güvenlik

- Hasta ifadesi klinik bulguya çevrilmez.
- Belirsiz rol, diş, kanal, durum veya kaynak varsa tahmin yapılmaz; hekimden
  onay istenir.
- Kodları LLM üretmez; adaylar kapalı/versionlanmış kod kaynağından gelir.
- Tüm çıktı taslaktır; hekim onayı olmadan klinik geçerlilik kazanmaz.

### MVP davranışı

V1 batch çalışır: `Görüşmeyi Başlat` → `Görüşmeyi Bitir` → kayıt işlenir →
role gate gerekiyorsa hekim onayı → klinik not/procedure/kod review.

## 2. Dikte: Periodontal çizelgeleme

### Amaç

Hekim periodontal muayene sırasında probla ilerlerken değerleri sesli dikte eder.
Tandela cep derinliklerini ve perio işaretlerini diş/bölge bazlı periodontal chart
taslağına dönüştürür.

### Çıktılar

- Dikte transkripti.
- Diş bazlı perio chart taslağı.
- Altı bölgeli format:
  - `MB` mesiobukkal,
  - `B` bukkal,
  - `DB` distobukkal,
  - `ML` mesiolingual/mesiopalatinal,
  - `L` lingual/palatinal,
  - `DL` distolingual/distopalatinal.
- Bölge başına desteklenen alanlar:
  - cep derinliği,
  - kanama/BOP,
  - plak,
  - furkasyon.
- Eksik, olağan dışı veya belirsiz değerler için review uyarısı.

### Güvenlik

- Net diş veya bölge yoksa değer tahmin edilmez.
- Olağan dışı cep değerleri ve eksik bölgeler hekim review için işaretlenir.
- Dikte edilen her değer taslaktır; hekim onayı gerekir.

### MVP davranışı

V1 demo slice batch çalışır: `Dikteyi Başlat` → `Dikteyi Bitir` → kayıt işlenir
→ perio chart taslağı doldurulur. Tam gerçek zamanlı dolum ve sesli düzeltme V2
kapsamına ayrılır.
