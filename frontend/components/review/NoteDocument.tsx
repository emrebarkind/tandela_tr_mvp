"use client";

import { AlertTriangle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type Role = "dentist" | "patient" | "assistant_or_other" | "unknown";
type NoteSectionId = "patient_complaint" | "history" | "clinical_findings" | "assessment" | "treatment_plan" | "procedures_note";

type NoteSectionLine = {
  text: string;
  source_quote?: string;
  source_role?: Role;
  source_speaker?: string | null;
  source_role_confidence?: "clear" | "uncertain";
};

type NoteSection = {
  id: NoteSectionId;
  title: string;
  lines: NoteSectionLine[];
};

type DocumentLine = NoteSectionLine & {
  sourceSectionId: NoteSectionId;
  sourceLineIndex: number;
};

type DocumentSection = {
  id: string;
  title: string;
  lines: DocumentLine[];
};

type NoteDocumentProps = {
  sections: NoteSection[];
  uncertainItems: string[];
  onSentenceChange: (sectionId: NoteSectionId, lineIndex: number, text: string) => void;
  onSourceRoleChange?: (speakerId: string, role: Role) => void;
};

const documentTitles: Record<NoteSectionId, string> = {
  patient_complaint: "Şikayet ve Anamnez",
  history: "Şikayet ve Anamnez",
  clinical_findings: "Klinik Bulgular",
  assessment: "Değerlendirme",
  treatment_plan: "Tedavi Planı",
  procedures_note: "İşlemler",
};

const roleLabels: Record<Role, string> = {
  dentist: "Hekim",
  patient: "Hasta",
  assistant_or_other: "Asistan / Diğer",
  unknown: "Bilinmiyor",
};

export function NoteDocument({ sections, uncertainItems, onSentenceChange, onSourceRoleChange }: NoteDocumentProps) {
  const mergedSections = mergeComplaintAndHistory(sections);

  return (
    <Card className="min-h-[760px] border-border bg-card p-7 shadow-card md:p-10">
      <div className="mb-10 flex flex-wrap items-start justify-between gap-4 border-b border-border pb-7">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Klinik Not Taslağı</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-foreground">Kapsamlı Muayene</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">Cümleleri doğrudan düzenleyebilirsiniz; kaynak alıntıları korunur.</p>
        </div>
        <span className="rounded-full bg-secondary px-3 py-1.5 text-xs font-semibold text-foreground">
          Hekim onayı bekliyor
        </span>
      </div>

      <div className="space-y-10">
        {mergedSections.map((section) => (
          <section key={section.id}>
            <h2 className="text-lg font-semibold text-foreground">{section.title}</h2>
            <div className="mt-4 space-y-4">
              {section.lines.map((line, lineIndex) => (
                <div key={`${section.id}-${lineIndex}`} className="border-l-2 border-ring pl-4">
                  <div className="flex items-start gap-2">
                    {line.source_role_confidence === "uncertain" ? (
                      <AlertTriangle className="mt-1 size-4 shrink-0 text-primary" aria-label="Konuşmacı rolü kontrol edilmeli" />
                    ) : null}
                    <textarea
                      className="min-h-[58px] w-full resize-y border-0 bg-transparent p-0 text-[15px] leading-7 text-foreground outline-none"
                      value={line.text}
                      onChange={(event) => onSentenceChange(line.sourceSectionId, line.sourceLineIndex, event.target.value)}
                      aria-label={`${section.title} taslak cümlesi`}
                    />
                  </div>
                  {shouldShowSourceQuote(section.lines, lineIndex) ? (
                    <p className="mt-1 text-sm italic leading-6 text-muted-foreground">
                      Kaynak: {roleLabels[line.source_role ?? "unknown"]}: {line.source_quote}
                    </p>
                  ) : null}
                  {line.source_role_confidence === "uncertain" && line.source_speaker ? (
                    <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-secondary bg-secondary px-3 py-2 text-xs text-foreground">
                      <span>
                        Bu cümle Speaker {line.source_speaker}'e ait. Rolü:
                      </span>
                      <Select
                        value={line.source_role ?? "unknown"}
                        onValueChange={(value) => onSourceRoleChange?.(line.source_speaker!, value as Role)}
                      >
                        <SelectTrigger className="h-8 w-[160px] border-secondary bg-card text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="dentist">Hekim</SelectItem>
                          <SelectItem value="patient">Hasta</SelectItem>
                          <SelectItem value="assistant_or_other">Asistan</SelectItem>
                          <SelectItem value="unknown">Bilinmiyor</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </section>
        ))}

        {uncertainItems.length ? (
          <section>
            <h2 className="text-lg font-semibold text-foreground">Kontrol Edilmeli</h2>
            <div className="mt-4 space-y-3">
              {uncertainItems.map((item) => (
                <p key={item} className="border-l-2 border-secondary pl-4 text-base leading-7 text-foreground">
                  {item}
                </p>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </Card>
  );
}

function shouldShowSourceQuote(lines: DocumentLine[], lineIndex: number) {
  const line = lines[lineIndex];
  if (!line.source_quote) return false;
  const previous = lines[lineIndex - 1];
  return !previous || previous.source_quote !== line.source_quote || previous.source_role !== line.source_role;
}

function mergeComplaintAndHistory(sections: NoteSection[]): DocumentSection[] {
  const visible = sections.filter((section) => section.lines.length);
  const complaint = visible.find((section) => section.id === "patient_complaint");
  const history = visible.find((section) => section.id === "history");
  const mergedComplaintHistory =
    complaint || history
      ? [{
          id: "complaint-history",
          title: "Şikayet ve Anamnez",
          lines: [
            ...(complaint?.lines.map((line, index) => ({ ...line, sourceSectionId: "patient_complaint" as NoteSectionId, sourceLineIndex: index })) ?? []),
            ...(history?.lines.map((line, index) => ({ ...line, sourceSectionId: "history" as NoteSectionId, sourceLineIndex: index })) ?? []),
          ],
        }]
      : [];
  return [
    ...mergedComplaintHistory,
    ...visible
      .filter((section) => section.id !== "patient_complaint" && section.id !== "history")
      .map((section) => ({
        id: section.id,
        title: documentTitles[section.id],
        lines: section.lines.map((line, index) => ({ ...line, sourceSectionId: section.id, sourceLineIndex: index })),
      })),
  ];
}
