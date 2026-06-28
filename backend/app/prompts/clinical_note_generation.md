# clinical_note_generation — prompt (TODO)

> Henüz yazılmadı. Beyin katmanının 3. aşaması (CLAUDE.md §3).

Görev: yalnızca fact JSON'undan taslak not üret — **yeni bilgi yok**.

Kilit kurallar (CLAUDE.md §4):
- Status çelişikse `unclear` + `uncertain_items`; tahmin etme.
- Her şey taslaktır; hekim onayı olmadan klinik geçerli sayılmaz.

Girdi: `app.pipeline.types.ClinicalFactsBundle`
Çıktı sözleşimi: `app.pipeline.types.ClinicalNoteDraft`.
