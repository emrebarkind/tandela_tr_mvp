# Dental Chart NLU Spec

Bu spec, dental chart taslağı için konuşmadan yapılandırılmış diş bulgusu çıkarma
kurallarını tanımlar. Aural reposundaki dental NLU yaklaşımı referans alınmıştır;
mimari, runtime veya veri akışı taşınmamıştır. Tandela TR için hedef stack:
FastAPI pipeline + Gemini LLM provider + mevcut REVIEW GATE ve §4 güvenlik
kurallarıdır.

## Amaç

Hekim konuşmasından yalnızca açıkça belgelenmiş dental chart öğelerini çıkarmak:

- FDI diş numarası
- Yüzeyler: `O`, `M`, `D`, `V`, `L`
- Yüzey bazlı kondisyonlar: çürük, kompozit, amalgam, inlay, onlay
- Diş bazlı etiketler: kron, köprü, protez, implant, kanal tedavisi, çekilmiş
- Durum: planlandı, yapıldı, tartışıldı, belirsiz
- Kaynak alıntı ve belirsizlik

Hasta ifadesi tek başına klinik bulguya dönüşmez. Hekim doğrulamadıkça chart
bulgusu yazılmaz.

## FDI Referansı

ISO 3950 / FDI iki haneli diş numarası kullanılır:

- `11-18`: üst sağ
- `21-28`: üst sol
- `31-38`: alt sol
- `41-48`: alt sağ

Geçerli FDI aralığı dışında numara üretilmez. Mırıltı, eksik hece veya güvenilir
olmayan STT çıktısından diş numarası tahmin edilmez.

Türkçe doğal dil eşleştirme örnekleri:

- `sağ üst bir` -> `11`
- `sağ üst sekiz` -> `18`
- `sol üst bir` -> `21`
- `sol üst sekiz` -> `28`
- `sol alt bir` -> `31`
- `sol alt sekiz` -> `38`
- `sağ alt bir` -> `41`
- `sağ alt altı` -> `46`
- `kırk altı`, `kirk alti`, `dört altı`, `4 6` -> `46`
- `otuz altı`, `üç altı`, `3 6` -> `36`

## Yüzey Notasyonu

Standart yüzey kodları:

| Kod | Anlam | Türkçe / STT varyantları |
| --- | --- | --- |
| `O` | occlusal | okluzal, oklüzal, oküzal, ok lüzal, çiğneme yüzeyi |
| `M` | mesial | mezial, meziyal, mesyal, mesial |
| `D` | distal | distal, distel, dıştal |
| `V` | vestibular/buccal | vestibül, vestibüler, bukkal, bukal, yanak tarafı |
| `L` | lingual/palatal | lingual, lingual/palatinal, palatinal, dil tarafı, damak tarafı |

`B` kullanılmaz; bu ürün `V` ile vestibular/buccal yüzeyi temsil eder.

## Bileşik Yüzey Parsing

Tek komutta birden fazla yüzey ayrıştırılabilir:

- `MOD` -> `M`, `O`, `D`
- `MO` -> `M`, `O`
- `OD` -> `O`, `D`
- `OV` -> `O`, `V`
- `bukkal ve lingual` -> `V`, `L`
- `mezial okluzal distal` -> `M`, `O`, `D`
- `üç yüzlü MOD kompozit` -> `M`, `O`, `D`, kondisyon `composite`

Bileşik parsing yapılırken yüzey sayısı ile yüzey isimleri çelişirse
`unclear`/review gerekir. Örn. “iki yüzlü MOD” hem iki yüz hem üç yüz içerdiği
için hekime gösterilmelidir.

## Türkçe STT Düzeltmeleri

NLU prompt'u STT hatalarını zihinsel olarak normalize eder, fakat güvenlik
kuralı olarak belirsiz veriden yeni klinik bulgu uydurmaz.

Örnek düzeltmeler:

- `kırk altı`, `kirk alti`, `dört altı` -> diş `46`
- `otuz altı`, `üç altı` -> diş `36`
- `meziyal`, `mezial`, `mesyal` -> `M`
- `okluzal`, `oklüzal`, `oküzal` -> `O`
- `bukkal`, `bukal`, `vestibül`, `vestibüler` -> `V`
- `lingual`, `palatinal`, `damak tarafı`, `dil tarafı` -> `L`
- `çürük`, `curuk`, `caries`, `karyes` -> `caries`
- `kompozit`, `kompo zit`, `dolgu` -> `composite` yalnızca hekim dolgu/
  restorasyon materyalini açıkça kompozit olarak söylüyorsa; aksi halde
  condition `unclear` kalabilir.
- `kanal`, `kanal tedavisi`, `endodontik tedavi` -> tooth label/procedure
  `rct` veya `kanal_tedavisi`
- `çekim`, `çekildi`, `eksik diş` -> `missing`/`dis_cekimi` bağlama göre
  ayrıştırılır; yapılmış mı planlanmış mı belirsizse `status=unclear`.

## Negation Handling

Olumsuz ifadeler chart bulgusu olarak yazılmaz:

- `çürük yok`
- `kanama yok`
- `mobilite yok`
- `perküsyon hassasiyeti yok`
- `radyografide lezyon yok`
- `46'da çürük yok, 47'de var` -> sadece `47` için bulgu çıkarılır.

Hasta sorusu veya endişesi bulgu değildir:

- Hasta: “Dişim iltihaplı mı?” -> chart bulgusu `infection` yazılamaz.
- Hekim: “Periapikal bölgede şüpheli görüntü var” -> belirsizlik korunur,
  kesin lezyon/tanıya çevrilmez.

Olumsuzluk kapsamı mümkünse cümle içinde tutulur. Kapsam belirsizse chart
bulgusu eklenmez; `uncertain_items` içine alınır.

## Gemini Prompt Çıktı Kontratı

Dental chart NLU aşaması eklendiğinde model yalnız JSON döndürmelidir:

```json
{
  "items": [
    {
      "tooth_number_fdi": 46,
      "surfaces": ["M", "O", "D"],
      "condition": "caries",
      "whole_tooth_labels": [],
      "status": "confirmed",
      "source_role": "dentist",
      "source_quote": "46 numarada MOD çürük görüyorum",
      "is_uncertain": false
    }
  ],
  "uncertain_items": []
}
```

Kurallar:

- `source_role` dentist değilse klinik chart bulgusu üretme.
- `source_quote` zorunlu.
- FDI doğrulaması zorunlu.
- Belirsiz yüzey, kondisyon veya status varsa alanı `unclear` yap veya
  `uncertain_items` içine taşı.
- Kod, işlem veya kondisyon uydurma; kapalı enum dışına çıkma.
- Sayısal confidence üretme.

## ProcedureObject Genişletme Önerisi

Backend `ProcedureObject` şu anda `surface_count` tutuyor, fakat yüzey isimlerini
tutmuyor. Dental chart için önerilen ek alanlar:

```python
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
    UNCLEAR = "unclear"


class ProcedureObject(BaseModel):
    procedure_family: str
    tooth_number_fdi: Optional[int] = None
    surface_count: Optional[SurfaceCount] = None
    surfaces: list[ToothSurface] = Field(default_factory=list)
    condition: Optional[DentalCondition] = None
    canal_count: Optional[CanalCount] = None
    status: ProcedureStatus = ProcedureStatus.UNCLEAR
    source_quotes: list[str] = Field(default_factory=list)
```

Bu değişiklik henüz uygulanmadı. Uygulamadan önce eval ve code matching etkisi
ayrı fazda ele alınmalıdır.
