import type { PatientInformation } from "@/components/review/PatientRecordPanel";

export type PatientRecordEdit = {
  field: keyof PatientInformation;
  value: string;
  label: string;
};

export function parsePatientRecordEditCommand(command: string): PatientRecordEdit | null {
  const occupationMatch = command.match(/\bmesle(?:ğ|g)i\s+([^,.;]+?)(?=\s*,|\s+[A-Za-zÇĞİÖŞÜçğıöşü]+\s+değil\b|$)/i);
  if (occupationMatch?.[1]?.trim()) {
    return { field: "occupation", value: occupationMatch[1].trim(), label: "Meslek" };
  }
  return null;
}
