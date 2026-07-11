# Perio araştırma notları

Bu dosya, Tandela Perio dikte şeması için referans niteliğindedir. Klinik
uygulama veya tanı protokolü değildir; ürün veri sözleşmesi hazırlanırken
kaynak ve kavram kontrolü için saklanır.

## Kaynaklar

- Periodontal Chart Online, "Calibration for Clinical Recording of Periodontal
  Status": https://www.periodontalchart-online.com/?lang=en-gb
- Hamp SE, Nyman S, Lindhe J. *Periodontal treatment of multirooted teeth.
  Results after 5 years.* J Clin Periodontol. 1975;2:126-135.
- Miller SC. *Textbook of Periodontia*, 3rd ed. 1950.
- ZoliQua/React-Odontogram-Modul kaynak kodu ve README:
  https://github.com/ZoliQua/React-Odontogram-Modul

## Altı ölçüm noktası

Her diş/implant için altı site kullanılır: MB, B, DB, ML, L, DL.
Referans site, her bölümde en yüksek probing değerinin kaydedilmesini anlatır.

## Attachment level hesaplaması

Ham ölçümler:

- `pocket_depth_mm`: gingival margin ile sulkus/cep tabanı arasındaki mesafe.
- `gingival_margin_mm`: gingival margin ile CEJ veya tanımlı referans noktası
  arasındaki mesafe. Recession durumunda negatif işaretlidir.

Türetilen değer:

```text
attachment_level_mm = pocket_depth_mm - gingival_margin_mm
```

Örnekler:

- 2 mm probing depth, 2 mm gingival margin -> 0 mm attachment level.
- 7 mm probing depth, 2 mm gingival margin -> 5 mm attachment level.
- 2 mm probing depth, -4 mm gingival margin -> 6 mm attachment level.

Bu hesap LLM'e verilmez. LLM yalnızca iki ham ölçümü kaynak alıntısıyla
çıkarabilir; backend türetilen değeri deterministik hesaplar.

## Furcation: Hamp 1975

Furkasyon derecesi 0-3'tür:

- 0: Furkasyon girişi saptanmaz.
- 1: Giriş saptanır; horizontal penetrasyon <= 3 mm.
- 2: Horizontal penetrasyon > 3 mm, tam geçiş yoktur.
- 3: Through-and-through açıklık vardır.

Furkasyon diş düzeyinde saklanır; giriş yönü ayrıca belirtilir (ör. buccal,
lingual/palatal veya mesial). Üründe yalnızca molarlarda ve daimi ilk
premolar istisnasında anlamlı kabul edilir.

## Mobility: Miller 1950

Mobility, site değil diş düzeyi alanıdır ve 0-3'tür:

- 0: Fizyolojik hareketlilik.
- 1: Horizontal hareketlilik <= 1 mm.
- 2: Horizontal hareketlilik > 1 mm.
- 3: Şiddetli, vertikal hareketlilik.

## Odontogram referansı

ZoliQua modülü yüzey bazlı dental charting için referans alınabilir: çürük
M/D/B/L/O ve subcrown katmanlarında, dolgular M/D/B/L/O katmanlarında tutulur.
Periodontal işareti yalnızca diş-düzeyi görsel overlay'dir; altı siteli perio
ölçüm şeması değildir.
