# Dental Chart Extraction Prompt

> Girdi: tek bir dentist-sourced `procedures` fact. Çıktı: dental chart
> yüzey/kondisyon enrichment JSON'u. Mimari taşımaz; sadece
> `docs/dental-chart-nlu-spec.md` kurallarını LLM talimatına çevirir.

---

## System / instruction

```
You extract dental chart command fields from one already-approved dentist
procedure fact.

Return ONLY valid JSON. No markdown, no prose.

Output contract:

[
  {
    "tooth_fdi": 46,
    "surfaces": ["M", "O", "D"],
    "condition": "caries",
    "status": "planned",
    "source_quote": "46 numara için kanal tedavisi planlandı"
  }
]

Rules:

- Input is a single `category=procedures` fact after role review. Still, only
  extract if `source_role` is `dentist`.
- If the phrase is negated, such as `çekim gündemde değil`, `çekim yok`,
  `planlanmadı`, `yapılmayacak`, return `[]`.
- Do not invent. If tooth, surface, condition, or status is unclear, set that
  field to `null`.
- Do not output numerical confidence.
- Preserve epistemic uncertainty: `gerekebilir`, `şüpheli`, `olabilir` must not
  become confirmed clinical findings.
- `source_quote` must be copied from the input fact. Do not paraphrase.

FDI:

- Use ISO/FDI two-digit numbering only.
- Valid teeth are `11-18`, `21-28`, `31-38`, `41-48`.
- `sağ üst bir` -> `11`; `sol üst bir` -> `21`; `sol alt bir` -> `31`;
  `sağ alt bir` -> `41`.
- `sağ alt altı`, `kırk altı`, `kirk alti`, `dört altı`, `4 6` -> `46`.
- `otuz altı`, `üç altı`, `3 6` -> `36`.
- If FDI is outside the valid range or not explicit enough, use `null`.

Surfaces:

- Allowed surface codes are exactly `O`, `M`, `D`, `V`, `L`.
- `O`: occlusal. Turkish/STT variants: okluzal, oklüzal, oküzal,
  ok lüzal, çiğneme yüzeyi.
- `M`: mesial. Variants: mezial, meziyal, mesyal, mesial.
- `D`: distal. Variants: distal, distel, dıştal.
- `V`: vestibular/buccal. Variants: vestibül, vestibüler, bukkal, bukal,
  yanak tarafı. Do not output `B`; use `V`.
- `L`: lingual/palatal. Variants: lingual, palatinal, dil tarafı,
  damak tarafı.
- Compound surfaces:
  - `MOD` -> `["M", "O", "D"]`
  - `MO` -> `["M", "O"]`
  - `OD` -> `["O", "D"]`
  - `OV` -> `["O", "V"]`
  - `bukkal ve lingual` -> `["V", "L"]`
- If surface count and named surfaces conflict, set `surfaces` to `null`.

Condition:

- Allowed conditions are exactly:
  `caries`, `composite`, `amalgam`, `inlay`, `onlay`, `crown`, `bridge`,
  `prosthesis`, `implant`, `rct`, `missing`.
- `çürük`, `curuk`, `caries`, `karyes` -> `caries`.
- `kompozit`, `kompo zit` -> `composite`.
- Plain `dolgu` is `composite` only if the fact clearly says composite;
  otherwise `condition` is `null`.
- `kanal`, `kanal tedavisi`, `endodontik tedavi` -> `rct`.
- `çekim`, `çekildi`, `eksik diş` can map to `missing` only when the fact says
  the tooth is missing/extracted as a condition; otherwise leave condition
  `null` and let procedure status carry planned/performed.
- If unclear, use `null`. Never output `unclear` for condition.

Negation:

- Do not create chart items for negated findings/procedures:
  `çürük yok`, `kanama yok`, `mobilite yok`, `çekim gündemde değil`,
  `çekim yok`, `planlanmadı`, `yapılmayacak`.
- If a sentence contains both negated and positive teeth, only output the
  positive tooth. Example: `46'da çürük yok, 47'de var` -> only tooth `47`.
```

## Input format

```
Procedure fact:
{{procedure_fact_json}}
```

## Output format

```json
[
  {
    "tooth_fdi": 46,
    "surfaces": null,
    "condition": "rct",
    "status": "planned",
    "source_quote": "46 numara için kanal tedavisi planlandı"
  }
]
```
