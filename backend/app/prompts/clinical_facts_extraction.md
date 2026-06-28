# clinical_facts_extraction — prompt (TODO)

> Henüz yazılmadı. Beyin katmanının 2. aşaması (CLAUDE.md §3).

Görev: transkriptten **kanıtlı** fact + provenance çıkar.

Kilit kurallar (CLAUDE.md §4):
- Hasta lafı klinik bulgu olamaz (yalnızca `patient_complaint`/`history`).
- Epistemik belirsizlik korunur ("şüpheli/olabilir" kesinleştirilmez).
- Her fact'te `source_quote` zorunlu.
- FDI diş numarası doğrulanır (11–48, geçerli çeyrek); mırıltıdan üretilmez.

Çıktı sözleşimi: `app.pipeline.types.ClinicalFactsBundle`.
Aşama 2→3 kontratı: fact metni yeniden yazılmaz, taşınır; `source_quote`
baştan sona korunur.
