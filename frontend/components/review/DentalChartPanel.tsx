"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Odontogram, type ToothConditionGroup } from "react-odontogram";
import "react-odontogram/style.css";

type ToothSurface = "O" | "M" | "D" | "V" | "L";

type ProcedureObject = {
  procedure_family: string;
  tooth_number_fdi?: number | null;
  surfaces?: ToothSurface[] | null;
  surface?: ToothSurface | ToothSurface[] | null;
  condition?: string | null;
  status: string;
};

type DentalConditionChip = {
  key: string;
  tooth: number | null;
  surfaces: ToothSurface[];
  condition: string;
  color: string;
};

type DentalChartPanelProps = {
  procedures: ProcedureObject[];
  approved: boolean;
};

const conditionColors: Record<string, string> = {
  caries: "#D4503A",
  composite: "#5A96C8",
  amalgam: "#7A7A7A",
  crown: "#E49545",
  implant: "#4A86C2",
  rct: "#7A5A8C",
  missing: "#D8DDE5",
  kanal_tedavisi: "#7A5A8C",
  kompozit_dolgu: "#5A96C8",
  dis_cekimi: "#D8DDE5",
  gecici_restorasyon: "#E49545",
  other: "#D4884A",
};

export function DentalChartPanel({ procedures, approved }: DentalChartPanelProps) {
  const chart = adaptProceduresToChart(procedures);

  return (
    <Card className="overflow-hidden border-[#DDE3E0] bg-white shadow-sm">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b border-[#DDE3E0] px-5 py-4">
        <div>
          <CardTitle className="text-base font-semibold tracking-tight text-[#202422]">Diş Şeması</CardTitle>
          <p className="mt-1 text-xs font-medium text-[#6F7470]">FDI gösterim</p>
        </div>
        <Badge className="rounded-full bg-[#E49545]/15 px-2.5 py-1 text-[11px] font-semibold text-[#7A6221] hover:bg-[#E49545]/15">
          Taslak
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4 p-5">
        <div className="rounded-2xl border border-[#DDE3E0] bg-[#F8F9F7] p-3">
          <Odontogram
            teethConditions={chart.teethConditions}
            readOnly
            notation="FDI"
            showLabels
            showTooltip
            layout="square"
            styles={{ maxWidth: "100%" }}
          />
        </div>
        <div className="space-y-2">
          {chart.conditionChips.length ? chart.conditionChips.map((chip) => (
            <div key={chip.key} className="relative overflow-hidden rounded-xl bg-white p-3 pl-4 text-sm shadow-sm ring-1 ring-[#DDE3E0]">
              <span className="absolute left-0 top-0 h-full w-[3px]" style={{ backgroundColor: chip.color }} aria-hidden="true" />
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium text-[#202422]">{conditionLabel(chip.condition)}</p>
                  <p className="mt-1 font-semibold text-[#6F7470] tabular-nums">
                    FDI {chip.tooth ?? "Belirsiz"}{chip.surfaces.length ? ` · ${chip.surfaces.join(" ")}` : ""}
                  </p>
                </div>
                {!approved ? (
                  <span className="text-base font-semibold leading-none text-[#6F7470]" aria-hidden="true">
                    ×
                  </span>
                ) : null}
              </div>
            </div>
          )) : (
            <p className="rounded-lg border border-dashed border-[#DDE3E0] bg-[#F8F9F7] px-4 py-3 text-sm text-[#6F7470]">
              Henüz diş bazlı işlem işaretlenmedi. Analiz tamamlandığında FDI numarası geçen işlemler burada görünür.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function adaptProceduresToChart(procedures: ProcedureObject[]) {
  const grouped = new Map<string, { labelKey: string; teeth: Set<string> }>();
  const conditionChips: DentalConditionChip[] = [];

  procedures.forEach((procedure, index) => {
    const labelKey = conditionKey(procedure);
    const colorKey = conditionColors[labelKey] ? labelKey : "other";
    const tooth = procedure.tooth_number_fdi ?? null;
    const surfaces = normalizeSurfaces(procedure);
    conditionChips.push({
      key: `${index}-${procedure.procedure_family}-${tooth ?? "unknown"}-${surfaces.join("")}-${labelKey}`,
      tooth,
      surfaces,
      condition: procedure.condition || labelKey,
      color: conditionColors[colorKey] ?? conditionColors.other,
    });
    if (tooth) {
      const group = grouped.get(colorKey) ?? { labelKey: colorKey, teeth: new Set<string>() };
      group.teeth.add(`teeth-${tooth}`);
      grouped.set(colorKey, group);
    }
  });

  const teethConditions: ToothConditionGroup[] = Array.from(grouped.values()).map(({ labelKey, teeth }) => {
    const color = conditionColors[labelKey] ?? conditionColors.other;
    return {
      label: conditionLabel(labelKey),
      teeth: Array.from(teeth),
      fillColor: color,
      outlineColor: color,
    };
  });

  return { teethConditions, conditionChips };
}

function conditionKey(procedure: ProcedureObject) {
  if (procedure.condition && procedure.condition !== "unclear") return procedure.condition;
  if (procedure.procedure_family === "kanal_tedavisi") return "rct";
  if (procedure.procedure_family === "kompozit_dolgu") return "composite";
  if (procedure.procedure_family === "dis_cekimi") return "missing";
  return procedure.procedure_family || "other";
}

function normalizeSurfaces(procedure: ProcedureObject): ToothSurface[] {
  const raw = procedure.surfaces ?? procedure.surface;
  const values = Array.isArray(raw) ? raw : raw ? [raw] : [];
  return values.filter((value): value is ToothSurface => value === "O" || value === "M" || value === "D" || value === "V" || value === "L");
}

function conditionLabel(value: string) {
  if (value === "caries") return "Çürük";
  if (value === "composite") return "Kompozit";
  if (value === "amalgam") return "Amalgam";
  if (value === "crown") return "Kron";
  if (value === "implant") return "İmplant";
  if (value === "rct") return "Kanal";
  if (value === "missing") return "Eksik";
  if (value === "kanal_tedavisi") return "Kanal Tedavisi";
  if (value === "kompozit_dolgu") return "Kompozit Dolgu";
  if (value === "dis_cekimi") return "Diş Çekimi";
  if (value === "gecici_restorasyon") return "Geçici Restorasyon";
  return "Diğer";
}
