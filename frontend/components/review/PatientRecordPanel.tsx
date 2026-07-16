"use client";

import { Card } from "@/components/ui/card";

type Role = "dentist" | "patient" | "assistant_or_other" | "unknown";

export type SourcedTextField = {
  value: string;
  source_quote: string;
  source_role: Role;
  source_speaker: string;
  is_uncertain?: boolean;
};

export type SourcedMedicalHistoryField = {
  value: boolean | null;
  detail?: string | null;
  source_quote: string;
  source_role: Role;
  source_speaker: string;
  is_uncertain?: boolean;
};

export type PatientInformation = {
  display_name?: SourcedTextField | null;
  age?: SourcedTextField | null;
  national_id?: SourcedTextField | null;
  date_of_birth?: SourcedTextField | null;
  occupation?: SourcedTextField | null;
  address?: SourcedTextField | null;
  phone?: SourcedTextField | null;
  email?: SourcedTextField | null;
  referred_by?: SourcedTextField | null;
};

export type MedicalHistory = {
  chronic_illness?: SourcedMedicalHistoryField | null;
  regular_medication?: SourcedMedicalHistoryField | null;
  drug_allergy?: SourcedMedicalHistoryField | null;
  contagious_disease?: SourcedMedicalHistoryField | null;
};

type PatientRecordPanelProps = {
  patientInformation: PatientInformation;
  medicalHistory: MedicalHistory;
  onPatientFieldChange: (field: keyof PatientInformation, value: string) => void;
  onMedicalHistoryChange: (field: keyof MedicalHistory, value: boolean | null, detail: string) => void;
};

const patientFieldLabels: Array<[keyof PatientInformation, string]> = [
  ["display_name", "Ad / Soyad"], ["age", "Yaş"], ["national_id", "T.C. Kimlik No"],
  ["date_of_birth", "Doğum Tarihi"], ["occupation", "Meslek"], ["address", "Adres"],
  ["phone", "Telefon"], ["email", "E-posta"], ["referred_by", "Yönlendiren"],
];

const medicalFieldLabels: Array<[keyof MedicalHistory, string]> = [
  ["chronic_illness", "Kronik hastalık"], ["regular_medication", "Düzenli ilaç"],
  ["drug_allergy", "İlaç alerjisi"], ["contagious_disease", "Bulaşıcı hastalık"],
];

export function PatientRecordPanel({ patientInformation, medicalHistory, onPatientFieldChange, onMedicalHistoryChange }: PatientRecordPanelProps) {
  return (
    <Card className="border-border bg-card p-7 shadow-card md:p-10">
      <div className="border-b border-border pb-7">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Hasta Kaydı</p>
        <h1 className="mt-3 font-heading text-3xl font-semibold tracking-tight text-foreground">Kimlik ve Tıbbi Özgeçmiş</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">Boş alanlar opsiyoneldir. Hekim bilgileri doğrudan düzenleyebilir.</p>
      </div>

      <div className="mt-8 space-y-10">
        <section>
          <h2 className="font-heading text-lg font-semibold text-foreground">Kimlik Bilgileri</h2>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            {patientFieldLabels.map(([field, label]) => {
              const item = patientInformation[field];
              return (
                <label key={field} className="space-y-1.5 text-sm font-medium text-foreground">
                  <span>{label}</span>
                  <input
                    className="h-10 w-full rounded-lg border border-border bg-background px-3 font-normal outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
                    value={item?.value ?? ""}
                    onChange={(event) => onPatientFieldChange(field, event.target.value)}
                  />
                  {item?.source_quote ? <span className="block text-xs font-normal italic text-muted-foreground">Kaynak: {item.source_quote}</span> : null}
                </label>
              );
            })}
          </div>
        </section>

        <section>
          <h2 className="font-heading text-lg font-semibold text-foreground">Tıbbi Özgeçmiş</h2>
          <div className="mt-4 space-y-4">
            {medicalFieldLabels.map(([field, label]) => {
              const item = medicalHistory[field];
              return (
                <div key={field} className="grid gap-3 rounded-xl border border-border bg-background/50 p-4 md:grid-cols-[180px_140px_1fr] md:items-start">
                  <span className="text-sm font-medium text-foreground">{label}</span>
                  <select
                    className="h-10 rounded-lg border border-border bg-background px-3 text-sm"
                    value={item?.value === true ? "yes" : item?.value === false ? "no" : ""}
                    onChange={(event) => onMedicalHistoryChange(field, event.target.value === "yes" ? true : event.target.value === "no" ? false : null, item?.detail ?? "")}
                  >
                    <option value="">Belirtilmedi</option>
                    <option value="yes">Var / Evet</option>
                    <option value="no">Yok / Hayır</option>
                  </select>
                  <div>
                    <input
                      className="h-10 w-full rounded-lg border border-border bg-background px-3 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
                      placeholder="Detay (opsiyonel)"
                      value={item?.detail ?? ""}
                      onChange={(event) => onMedicalHistoryChange(field, item?.value ?? null, event.target.value)}
                    />
                    {item?.source_quote ? <span className="mt-1.5 block text-xs italic text-muted-foreground">Kaynak: {item.source_quote}</span> : null}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </Card>
  );
}
