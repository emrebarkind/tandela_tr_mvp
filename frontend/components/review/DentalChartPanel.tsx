"use client";

import { useState } from "react";
import { Plus, RotateCcw, ZoomIn } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Odontogram, type ToothConditionGroup } from "react-odontogram";
import "react-odontogram/style.css";

type ToothSurface = "O" | "M" | "D" | "V" | "L";
type DentalCondition = "caries" | "composite" | "amalgam" | "inlay" | "onlay" | "crown" | "bridge" | "prosthesis" | "implant" | "rct" | "missing";

type ProcedureObject = {
  procedure_family: string;
  tooth_number_fdi?: number | null;
  surfaces?: ToothSurface[] | null;
  surface?: ToothSurface | ToothSurface[] | null;
  condition?: string | null;
  status: string;
  source_quotes?: string[] | null;
  is_manual?: boolean;
  manual_note?: string | null;
};

type DentalConditionChip = {
  key: string;
  tooth: number | null;
  surfaces: ToothSurface[];
  condition: string;
  color: string;
  sourceQuote?: string | null;
  findingText: string;
};

type DentalChartPanelProps = {
  procedures: ProcedureObject[];
  approved: boolean;
  onAddFinding?: (finding: { tooth_number_fdi: number; condition: DentalCondition; note?: string }) => Promise<void> | void;
  layout?: "full" | "canvas";
  isLoading?: boolean;
};

const conditionColors: Record<string, string> = {
  caries: "var(--destructive)",
  composite: "var(--ring)",
  amalgam: "var(--muted-foreground)",
  crown: "var(--primary)",
  implant: "var(--ring)",
  rct: "var(--primary)",
  missing: "var(--border)",
  kanal_tedavisi: "var(--primary)",
  kompozit_dolgu: "var(--ring)",
  dis_cekimi: "var(--border)",
  gecici_restorasyon: "var(--primary)",
  other: "var(--muted-foreground)",
};

export function DentalChartPanel({ procedures, approved, onAddFinding, layout = "full", isLoading = false }: DentalChartPanelProps) {
  const chart = adaptProceduresToChart(procedures);
  const [isAdding, setIsAdding] = useState(false);
  const [toothNumber, setToothNumber] = useState("");
  const [condition, setCondition] = useState<DentalCondition>("caries");
  const [note, setNote] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  async function submitFinding() {
    const parsedTooth = Number.parseInt(toothNumber, 10);
    if (!isValidFdi(parsedTooth)) {
      setFormError("Geçerli bir FDI numarası girin: 11-48 veya 51-85 aralığında anlamlı diş olmalı.");
      return;
    }
    setIsSaving(true);
    setFormError(null);
    try {
      await onAddFinding?.({
        tooth_number_fdi: parsedTooth,
        condition,
        note: note.trim() || undefined,
      });
      setToothNumber("");
      setCondition("caries");
      setNote("");
      setIsAdding(false);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Bulgu eklenemedi.");
    } finally {
      setIsSaving(false);
    }
  }

  const chartCanvas = (
    <Card className="overflow-hidden border-border bg-card shadow-card">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 border-b border-border px-6 py-5">
        <div>
          <CardTitle className="text-lg font-semibold tracking-tight text-foreground">Anatomik Diş Şeması</CardTitle>
          <p className="mt-1 text-sm font-medium text-muted-foreground">FDI gösterim · hekim onayı bekleyen taslak</p>
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" variant="ghost" size="icon" className="rounded-lg text-muted-foreground hover:bg-secondary" aria-label="Yakınlaştır">
            <ZoomIn className="size-4" />
          </Button>
          <Button type="button" variant="ghost" size="icon" className="rounded-lg text-muted-foreground hover:bg-secondary" aria-label="Görünümü sıfırla">
            <RotateCcw className="size-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-5 p-6">
        <div className="min-h-[520px] rounded-2xl border border-border bg-background p-4 xl:min-h-[640px]">
          {isLoading ? (
            <DentalChartSkeleton />
          ) : (
            <Odontogram
              teethConditions={chart.teethConditions}
              readOnly
              notation="FDI"
              showLabels
              showTooltip
              layout="square"
              styles={{ maxWidth: "100%" }}
            />
          )}
        </div>
        <div className="flex flex-wrap gap-2 rounded-2xl border border-border bg-background p-3">
          {legendItems.map((item) => (
            <div key={item.key} className="flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5">
              <span className="size-3 rounded-full" style={{ backgroundColor: item.color }} aria-hidden="true" />
              <span className="text-xs font-semibold text-muted-foreground">{item.label}</span>
            </div>
          ))}
        </div>
        {chart.conditionChips.length ? (
          <div className="flex flex-wrap gap-2 rounded-2xl border border-border bg-card p-3">
            {chart.conditionChips.map((chip) => (
              <div key={chip.key} className="relative overflow-hidden rounded-lg border border-border bg-background py-2 pl-4 pr-3 shadow-card">
                <span className="absolute left-0 top-0 h-full w-[3px]" style={{ backgroundColor: chip.color }} aria-hidden="true" />
                <p className="text-xs font-semibold text-foreground">
                  {chip.findingText} · FDI <span className="tabular-nums">{chip.tooth ?? "Belirsiz"}</span>
                  {chip.surfaces.length ? <span className="ml-1 tabular-nums">{chip.surfaces.join(" ")}</span> : null}
                </p>
              </div>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );

  if (layout === "canvas") {
    return chartCanvas;
  }

  return (
    <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_300px] xl:grid-cols-[minmax(0,1fr)_380px]">
      {chartCanvas}

      <Card className="overflow-hidden border-border bg-card shadow-card">
        <CardHeader className="border-b border-border px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base font-semibold tracking-tight text-foreground">Bulgular ve Hekim Notları</CardTitle>
              <p className="mt-1 text-xs font-medium text-muted-foreground">Her kayıt kaynak alıntısıyla gösterilir.</p>
            </div>
            <Badge className="rounded-full bg-secondary px-2.5 py-1 text-[11px] font-semibold text-foreground hover:bg-secondary">
              Taslak
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 p-5">
          {chart.conditionChips.length ? chart.conditionChips.map((chip) => (
            <div key={chip.key} className="relative overflow-hidden rounded-xl bg-card p-4 pl-5 text-sm shadow-card ring-1 ring-border">
              <span className="absolute left-0 top-0 h-full w-[3px]" style={{ backgroundColor: chip.color }} aria-hidden="true" />
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold text-foreground">
                    FDI <span className="tabular-nums">{chip.tooth ?? "Belirsiz"}</span>
                  </p>
                  <p className="mt-1 text-sm font-medium text-muted-foreground">
                    {chip.findingText}{chip.surfaces.length ? ` · ${chip.surfaces.join(" ")}` : ""}
                  </p>
                  {chip.sourceQuote ? (
                    <p className="mt-3 text-xs italic leading-5 text-muted-foreground">Kaynak: {chip.sourceQuote}</p>
                  ) : null}
                </div>
                {!approved ? (
                  <span className="text-base font-semibold leading-none text-muted-foreground" aria-hidden="true">
                    ×
                  </span>
                ) : null}
              </div>
            </div>
          )) : (
            <p className="rounded-lg border border-dashed border-border bg-background px-4 py-3 text-sm text-muted-foreground">
              Henüz diş bazlı işlem işaretlenmedi. Analiz tamamlandığında FDI numarası geçen işlemler burada görünür.
            </p>
          )}
          {!approved ? (
            <div className="space-y-3">
              {isAdding ? (
                <div className="rounded-xl border border-border bg-background p-3">
                  <div className="grid gap-3">
                    <div>
                      <label className="text-xs font-semibold text-muted-foreground" htmlFor="manual-fdi">FDI numarası</label>
                      <Input
                        id="manual-fdi"
                        inputMode="numeric"
                        value={toothNumber}
                        onChange={(event) => setToothNumber(event.target.value)}
                        placeholder="Örn. 27"
                        className="mt-1 h-10 border-border bg-card"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-semibold text-muted-foreground">Kondisyon</label>
                      <Select value={condition} onValueChange={(value) => setCondition(value as DentalCondition)}>
                        <SelectTrigger className="mt-1 h-10 border-border bg-card">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {manualConditions.map((item) => (
                            <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <label className="text-xs font-semibold text-muted-foreground" htmlFor="manual-note">Not</label>
                      <Textarea
                        id="manual-note"
                        value={note}
                        onChange={(event) => setNote(event.target.value)}
                        placeholder="Opsiyonel hekim notu"
                        className="mt-1 min-h-[72px] resize-y border-border bg-card text-sm"
                      />
                    </div>
                    {formError ? <p className="text-xs font-medium text-destructive">{formError}</p> : null}
                    <div className="flex gap-2">
                      <Button type="button" className="h-9 flex-1 bg-primary text-primary-foreground hover:bg-primary/80" onClick={() => void submitFinding()} disabled={isSaving || !onAddFinding}>
                        Kaydet
                      </Button>
                      <Button type="button" variant="ghost" className="h-9 flex-1" onClick={() => setIsAdding(false)} disabled={isSaving}>
                        Vazgeç
                      </Button>
                    </div>
                  </div>
                </div>
              ) : (
                <Button type="button" variant="outline" className="h-10 w-full rounded-lg border-border bg-card text-primary hover:bg-secondary" onClick={() => setIsAdding(true)}>
                  <Plus className="mr-2 size-4" />
                  Yeni Bulgu Ekle
                </Button>
              )}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
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
      sourceQuote: procedure.source_quotes?.[0] ?? null,
      findingText: conditionLabel(procedure.condition || labelKey),
    });
    if (tooth) {
      const group = grouped.get(colorKey) ?? { labelKey: colorKey, teeth: new Set<string>() };
      const visualTooth = tooth >= 31 && tooth <= 38
        ? tooth + 10
        : tooth >= 41 && tooth <= 48
          ? tooth - 10
          : tooth;
      group.teeth.add(`teeth-${visualTooth}`);
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

function DentalChartSkeleton() {
  const teeth = Array.from({ length: 32 }, (_, index) => index);
  return (
    <div className="flex min-h-[480px] flex-col justify-start gap-10 pt-3">
      {[0, 1].map((row) => (
        <div key={row} className="grid grid-cols-[repeat(16,minmax(0,1fr))] gap-3">
          {teeth.slice(row * 16, row * 16 + 16).map((tooth) => (
            <Skeleton key={tooth} className="h-14 rounded-[45%] bg-muted" />
          ))}
        </div>
      ))}
      <div className="mt-auto space-y-3 rounded-2xl border border-dashed border-border bg-card/70 p-4">
        <Skeleton className="h-3 w-44 bg-muted" />
        <Skeleton className="h-3 w-72 bg-muted" />
      </div>
    </div>
  );
}

const legendItems = [
  { key: "caries", label: "Çürük", color: conditionColors.caries },
  { key: "composite", label: "Kompozit Dolgu", color: conditionColors.composite },
  { key: "crown", label: "Kron", color: conditionColors.crown },
  { key: "rct", label: "Kanal Tedavisi", color: conditionColors.rct },
  { key: "missing", label: "Eksik Diş", color: conditionColors.missing },
];

const manualConditions: { value: DentalCondition; label: string }[] = [
  { value: "caries", label: "Çürük" },
  { value: "composite", label: "Kompozit" },
  { value: "amalgam", label: "Amalgam" },
  { value: "inlay", label: "Inlay" },
  { value: "onlay", label: "Onlay" },
  { value: "crown", label: "Kron" },
  { value: "bridge", label: "Köprü" },
  { value: "prosthesis", label: "Protez" },
  { value: "implant", label: "İmplant" },
  { value: "rct", label: "Kanal Tedavisi" },
  { value: "missing", label: "Eksik Diş" },
];

function isValidFdi(value: number) {
  if (!Number.isInteger(value)) return false;
  const quadrant = Math.floor(value / 10);
  const tooth = value % 10;
  if ([1, 2, 3, 4].includes(quadrant)) return tooth >= 1 && tooth <= 8;
  if ([5, 6, 7, 8].includes(quadrant)) return tooth >= 1 && tooth <= 5;
  return false;
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
  if (value === "rct") return "Kanal Tedavisi";
  if (value === "missing") return "Eksik";
  if (value === "bridge") return "Köprü";
  if (value === "prosthesis") return "Protez";
  if (value === "inlay") return "Inlay";
  if (value === "onlay") return "Onlay";
  if (value === "kanal_tedavisi") return "Kanal Tedavisi";
  if (value === "kompozit_dolgu") return "Kompozit Dolgu";
  if (value === "dis_cekimi") return "Diş Çekimi";
  if (value === "gecici_restorasyon") return "Geçici Restorasyon";
  return "Diğer";
}
