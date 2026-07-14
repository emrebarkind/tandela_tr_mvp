"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Loader2,
  Mic,
  Play,
  Stethoscope,
  Waves,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Odontogram, type ToothConditionGroup, type ToothDetail } from "react-odontogram";
import "react-odontogram/style.css";

type PerioSite = "DB" | "B" | "MB" | "DL" | "L" | "ML";

type PerioMeasurement = {
  tooth_number_fdi: number;
  site: PerioSite;
  pocket_depth_mm: number | null;
  gingival_margin_mm: number | null;
  attachment_level_mm: number | null;
  bleeding_on_probing: boolean | null;
  plaque: boolean | null;
  recession_mm: number | null;
  source_quote: string;
  is_uncertain: boolean;
};

type ToothPerioSummary = {
  tooth_number_fdi: number;
  mobility_grade: number | null;
  furcation_grade: number | null;
  furcation_site: string | null;
};

type PerioToothVisual = {
  tooth: number;
  maxPocket: number | null;
  mobilityGrade: number | null;
  furcationGrade: number | null;
  furcationSite: string | null;
};

export type PerioSessionResult = {
  measurements: PerioMeasurement[];
  tooth_summaries: ToothPerioSummary[];
  uncertain_items: string[];
};

type PerioChartPanelProps = {
  sessionId: string;
  apiBase: string;
  authHeaders: Record<string, string>;
  initialResult?: PerioSessionResult | null;
};

const SITE_ORDER: PerioSite[] = ["DB", "B", "MB", "DL", "L", "ML"];
const BUCCAL_SITES: PerioSite[] = ["DB", "B", "MB"];
const LINGUAL_SITES: PerioSite[] = ["DL", "L", "ML"];

export function PerioChartPanel({ sessionId, apiBase, authHeaders, initialResult = null }: PerioChartPanelProps) {
  const dictationRef = useRef<HTMLTextAreaElement | null>(null);
  const [dictation, setDictation] = useState("");
  const [result, setResult] = useState<PerioSessionResult | null>(initialResult);
  const [selectedTooth, setSelectedTooth] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setResult(initialResult);
  }, [initialResult]);

  const teeth = useMemo(() => {
    if (!result) return [];
    return Array.from(
      new Set([
        ...result.measurements.map((item) => item.tooth_number_fdi),
        ...result.tooth_summaries.map((item) => item.tooth_number_fdi),
      ]),
    ).sort((a, b) => a - b);
  }, [result]);

  useEffect(() => {
    if (teeth.length && (selectedTooth === null || !teeth.includes(selectedTooth))) {
      setSelectedTooth(teeth[0]);
    }
  }, [selectedTooth, teeth]);

  const measurements = useMemo(
    () => result?.measurements.filter((item) => item.tooth_number_fdi === selectedTooth) ?? [],
    [result, selectedTooth],
  );
  const bySite = useMemo(() => new Map(measurements.map((item) => [item.site, item])), [measurements]);
  const summary = result?.tooth_summaries.find((item) => item.tooth_number_fdi === selectedTooth) ?? null;
  const toothVisuals = useMemo(() => {
    if (!result) return [];
    return teeth.map((tooth): PerioToothVisual => {
      const toothMeasurements = result.measurements.filter((item) => item.tooth_number_fdi === tooth);
      const toothSummary = result.tooth_summaries.find((item) => item.tooth_number_fdi === tooth);
      return {
        tooth,
        maxPocket: maxNumber(toothMeasurements.map((item) => item.pocket_depth_mm)),
        mobilityGrade: toothSummary?.mobility_grade ?? null,
        furcationGrade: toothSummary?.furcation_grade ?? null,
        furcationSite: toothSummary?.furcation_site ?? null,
      };
    });
  }, [result, teeth]);
  const selectedMetrics = useMemo(() => getToothMetrics(measurements), [measurements]);
  const sourceQuotes = useMemo(() => measurements.filter((item) => item.source_quote).slice(0, 3), [measurements]);

  async function analyze() {
    if (!dictation.trim()) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase}/sessions/${sessionId}/perio`, {
        method: "POST",
        headers: { ...authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify({ dictation: dictation.trim() }),
      });
      if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
      const nextResult = (await response.json()) as PerioSessionResult;
      setResult(nextResult);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Perio taslağı hazırlanamadı.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="space-y-5 font-body text-foreground">
      <Card className="gap-0 py-0">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-6 py-5 lg:px-8">
          <div className="flex items-center gap-4">
            <div className="flex size-11 items-center justify-center rounded-xl bg-secondary text-primary">
              <Waves className="size-5" />
            </div>
            <div>
              <h2 className="font-heading text-xl font-semibold">Periodontal Çizelgeleme</h2>
              <p className="mt-1 text-sm text-muted-foreground">Altı nokta ölçümlerinden incelemeye hazır taslak</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-2 text-xs font-semibold text-muted-foreground">
              <span className={`size-2 rounded-full ${result ? "bg-primary" : "bg-border"}`} />
              {result ? "Analiz hazır" : "Dikte bekleniyor"}
            </span>
          </div>
        </header>

        <div className="grid gap-5 bg-background p-5 lg:grid-cols-[minmax(0,1fr)_240px] lg:p-6">
          <div className="relative">
            <Mic className="pointer-events-none absolute left-4 top-4 size-4 text-primary" />
            <Textarea
              ref={dictationRef}
              value={dictation}
              onChange={(event) => setDictation(event.target.value)}
              placeholder="Örn. 16 bukkal üç dört dört, kanama yok, plak var. Mobilite bir, furkasyon iki bukkal."
              className="min-h-32 resize-y rounded-xl border-border bg-card py-4 pl-11 pr-4 text-sm leading-6 shadow-none placeholder:text-muted-foreground focus-visible:ring-ring"
            />
          </div>
          <div className="flex flex-col justify-between gap-4">
            <p className="text-sm leading-6 text-muted-foreground">Yalnızca açıkça dikte edilen ölçümler eklenir. Belirsiz alanlar boş bırakılır.</p>
            <Button
              type="button"
              onClick={() => void analyze()}
              disabled={isLoading || !dictation.trim()}
              className="h-11 rounded-xl bg-primary px-5 font-semibold text-primary-foreground shadow-none hover:bg-primary/90"
            >
              {isLoading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Stethoscope className="mr-2 size-4" />}
              Analiz Et
            </Button>
          </div>
        </div>
      </Card>

      {error ? <p className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm font-medium text-destructive">{error}</p> : null}

      {result && selectedTooth ? (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.28 }}
          className="space-y-5"
        >
          <Card className="gap-0 py-0">
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-6 py-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">İncelenen diş</p>
                <h3 className="mt-1 font-heading text-2xl font-semibold">{selectedTooth} Numara</h3>
              </div>
              <div className="flex flex-wrap gap-2" aria-label="Ölçüm bulunan dişler">
                {teeth.map((tooth) => (
                  <button
                    key={tooth}
                    type="button"
                    onClick={() => setSelectedTooth(tooth)}
                    className={`h-9 min-w-10 rounded-lg border px-3 text-sm font-semibold tabular-nums transition-colors ${
                      tooth === selectedTooth
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border bg-card text-muted-foreground hover:bg-secondary"
                    }`}
                  >
                    {tooth}
                  </button>
                ))}
              </div>
            </div>
            <div className="bg-background p-4 md:p-6">
              <AnatomicalDentalArch toothVisuals={toothVisuals} selectedTooth={selectedTooth} onSelect={setSelectedTooth} />
            </div>
          </Card>

          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
            <MeasurementMatrix tooth={selectedTooth} bySite={bySite} />
            <ClinicalSummaryCard
              tooth={selectedTooth}
              metrics={selectedMetrics}
              summary={summary}
              uncertainItems={result.uncertain_items}
              sourceQuotes={sourceQuotes}
            />
          </div>
        </motion.div>
      ) : (
        <EmptyPerioState />
      )}

      {result?.uncertain_items.length ? (
        <Card className="border-amber-200 bg-amber-50/95 p-4 text-amber-950">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="mb-2 flex items-center gap-2 font-heading font-semibold">
                <AlertTriangle className="size-4" />
                Kontrol Edilmeli
              </div>
              <ul className="space-y-1 text-sm">{result.uncertain_items.map((item, index) => <li key={`${item}-${index}`}>• {item}</li>)}</ul>
            </div>
            <Button variant="outline" className="rounded-full border-amber-300 bg-card" onClick={() => dictationRef.current?.focus()}>
              Hemen Düzelt
            </Button>
          </div>
        </Card>
      ) : null}
    </div>
  );
}

const MEASUREMENT_ROWS = [
  { label: "Cep derinliği", field: "pocket_depth_mm", suffix: "mm", heatmap: true },
  { label: "Gingival margin", field: "gingival_margin_mm", suffix: "mm" },
  { label: "Attachment level", field: "attachment_level_mm", suffix: "mm" },
  { label: "Kanama", field: "bleeding_on_probing" },
  { label: "Plak", field: "plaque" },
  { label: "Resesyon", field: "recession_mm", suffix: "mm" },
] as const;

function MeasurementMatrix({ tooth, bySite }: { tooth: number; bySite: Map<PerioSite, PerioMeasurement> }) {
  return (
    <Card className="gap-0 py-0">
      <div className="flex items-center justify-between border-b border-border px-6 py-5">
        <div>
          <h3 className="font-heading text-lg font-semibold">Periodontal ölçümler</h3>
          <p className="mt-1 text-sm text-muted-foreground">FDI {tooth} · altı nokta görünümü</p>
        </div>
        <Badge variant="outline" className="rounded-full">Altı nokta görünümü</Badge>
      </div>

      <div className="overflow-x-auto p-4 md:p-6">
        <table className="w-full min-w-[640px] border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              <th className="w-40 border-b border-border px-3 py-3 text-left text-xs font-semibold uppercase text-muted-foreground">Ölçüm</th>
              {SITE_ORDER.map((site, index) => (
                <th key={site} className={`border-b border-border px-3 py-3 text-center font-semibold ${index === 3 ? "border-l" : ""}`}>
                  <span className="block font-heading text-base">{site}</span>
                  <span className="mt-0.5 block text-[10px] font-normal text-muted-foreground">{index < 3 ? "Bukkal" : "Lingual"}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {MEASUREMENT_ROWS.map((row) => (
              <tr key={row.field}>
                <th className="border-b border-border/70 px-3 py-4 text-left font-medium text-muted-foreground">{row.label}</th>
                {SITE_ORDER.map((site, index) => {
                  const item = bySite.get(site);
                  const value = item?.[row.field] ?? null;
                  return (
                    <td key={site} className={`border-b border-border/70 p-1.5 text-center ${index === 3 ? "border-l" : ""}`}>
                      <PerioTableCell item={item} value={value} suffix={"suffix" in row ? row.suffix : undefined} heatmap={"heatmap" in row && row.heatmap} />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-2"><span className="size-2 rounded-full bg-secondary" /> 0–3 mm</span>
          <span className="flex items-center gap-2"><span className="size-2 rounded-full bg-amber-200" /> 4–5 mm / kontrol</span>
          <span className="flex items-center gap-2"><span className="size-2 rounded-full bg-destructive/20" /> 6+ mm</span>
        </div>
      </div>
    </Card>
  );
}

function PerioTableCell({ item, value, suffix, heatmap = false }: {
  item: PerioMeasurement | undefined;
  value: number | boolean | null;
  suffix?: string;
  heatmap?: boolean;
}) {
  const display = typeof value === "boolean" ? (value ? "✓" : "—") : value === null ? "—" : `${value}${suffix ? ` ${suffix}` : ""}`;
  const content = (
    <div className={`flex min-h-10 items-center justify-center rounded-lg px-2 font-medium tabular-nums ${measurementCellClass(item, value, heatmap)}`}>
      {display}
    </div>
  );
  if (!item?.source_quote) return content;
  return (
    <Tooltip>
      <TooltipTrigger render={content} />
      <TooltipContent className="max-w-sm">Kaynak: {item.source_quote}</TooltipContent>
    </Tooltip>
  );
}

function ClinicalSummaryCard({ tooth, metrics, summary, uncertainItems, sourceQuotes }: {
  tooth: number;
  metrics: ToothMetrics;
  summary: ToothPerioSummary | null;
  uncertainItems: string[];
  sourceQuotes: PerioMeasurement[];
}) {
  return (
    <Card className="gap-0 p-5 py-5">
      <div className="flex items-center gap-3 border-b border-border pb-4">
        <div className="flex size-10 items-center justify-center rounded-xl bg-secondary text-primary"><ClipboardCheck className="size-5" /></div>
        <div>
          <h3 className="font-heading font-semibold">Diş özeti</h3>
          <p className="text-xs text-muted-foreground">FDI {tooth}</p>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <SummaryValue label="En derin cep" value={metrics.maxPocket === null ? null : `${metrics.maxPocket} mm`} uncertain={false} />
        <SummaryValue label="Resesyon" value={metrics.maxRecession === null ? null : `${metrics.maxRecession} mm`} uncertain={false} />
        <SummaryValue label="Mobilite" value={summary?.mobility_grade ?? null} uncertain={isSummaryUncertain(uncertainItems, tooth, "mobilite")} />
        <SummaryValue label="Furkasyon" value={summary?.furcation_grade == null ? null : `${summary.furcation_grade}${summary.furcation_site ? ` · ${formatSite(summary.furcation_site)}` : ""}`} uncertain={isSummaryUncertain(uncertainItems, tooth, "furkasyon")} />
      </div>
      <div className="mt-4 flex gap-4 rounded-xl bg-background p-3">
        <BooleanMarker tone="error" label="Kanama" value={metrics.hasBleeding} />
        <BooleanMarker tone="warning" label="Plak" value={metrics.hasPlaque} />
      </div>
      <div className="mt-5">
        <p className="text-xs font-semibold uppercase text-muted-foreground">Kaynak</p>
        <div className="mt-2 space-y-2">
          {sourceQuotes.length ? sourceQuotes.map((item, index) => (
            <p key={`${item.site}-${index}`} className="rounded-xl border border-border bg-background p-3 text-sm italic leading-5 text-muted-foreground">
              “{item.source_quote}”
            </p>
          )) : <p className="text-sm text-muted-foreground">—</p>}
        </div>
      </div>
    </Card>
  );
}

function EmptyPerioState() {
  return (
    <Card className="gap-0 py-0">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-6 py-5">
        <div>
          <h3 className="font-heading text-lg font-semibold">Periodontal taslak</h3>
          <p className="mt-1 text-sm text-muted-foreground">Dikte analiz edildiğinde ölçüm bulunan dişler burada işaretlenir.</p>
        </div>
        <span className="rounded-full bg-secondary px-3 py-1 text-xs font-semibold text-muted-foreground">FDI görünümü</span>
      </div>

      <div className="grid gap-6 bg-background p-5 xl:grid-cols-[minmax(0,1fr)_300px] xl:p-6">
        <div className="space-y-5">
          <Card size="sm" className="gap-0 bg-card p-4 py-4">
            <div className="mb-3 flex items-center justify-between text-xs font-semibold uppercase text-muted-foreground">
              <span>Sağ</span>
              <span>Tam diş arkı</span>
              <span>Sol</span>
            </div>
            <AnatomicalDentalArch toothVisuals={[]} selectedTooth={null} />
          </Card>

          <Card size="sm" className="gap-0 overflow-x-auto bg-card p-4 py-4">
            <div className="min-w-[620px]">
              <div className="grid grid-cols-[160px_repeat(6,minmax(64px,1fr))] border-b border-border text-center text-xs font-semibold text-muted-foreground">
                <span className="px-3 py-3 text-left">Ölçüm</span>
                {SITE_ORDER.map((site) => <span key={site} className="px-2 py-3">{site}</span>)}
              </div>
              {MEASUREMENT_ROWS.map((row) => (
                <div key={row.field} className="grid grid-cols-[160px_repeat(6,minmax(64px,1fr))] border-b border-border/70 last:border-0">
                  <span className="px-3 py-4 text-sm font-medium text-muted-foreground">{row.label}</span>
                  {SITE_ORDER.map((site) => <BlankMeasurementCell key={`${row.field}-${site}`} label="" />)}
                </div>
              ))}
            </div>
          </Card>
        </div>

        <Card size="sm" className="gap-0 bg-card p-5 py-5">
          <div className="flex size-10 items-center justify-center rounded-xl bg-secondary text-primary">
            <ClipboardCheck className="size-5" />
          </div>
          <h3 className="mt-4 font-heading text-lg font-semibold">Klinik kontrol</h3>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">Ölçümler yalnızca açık dikteye göre doldurulur. Söylenmeyen alanlar boş kalır.</p>
          <div className="mt-5 space-y-2">
            <EmptySidebarRow label="Mobilite" />
            <EmptySidebarRow label="Furkasyon" />
            <EmptySidebarRow label="Kaynak alıntısı" />
          </div>
        </Card>
      </div>
    </Card>
  );
}

function DentalArchVisualizer({ teeth, selectedTooth, metrics, onSelect }: {
  teeth: number[];
  selectedTooth: number;
  metrics: ToothMetrics;
  onSelect: (tooth: number) => void;
}) {
  return (
    <Card className="gap-0 p-5 py-5 md:p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Stethoscope className="size-5 text-primary" />
          <h3 className="font-heading text-lg font-semibold uppercase text-foreground">Full Dental Arch (FDI)</h3>
        </div>
        <div className="flex items-center gap-3 text-xs font-semibold uppercase text-muted-foreground">
          <span>Sağ</span>
          <span className="h-3 w-px bg-border" />
          <span>Sol</span>
        </div>
      </div>
      <AnatomicalDentalArch
        toothVisuals={teeth.map((tooth) => ({
          tooth,
          maxPocket: tooth === selectedTooth ? metrics.maxPocket : null,
          mobilityGrade: null,
          furcationGrade: null,
          furcationSite: null,
        }))}
        selectedTooth={selectedTooth}
        onSelect={onSelect}
      />
      <div className="mt-4 flex flex-wrap items-center gap-3 text-xs font-medium text-muted-foreground">
        <span className="rounded-full bg-secondary px-3 py-1">Aktif: FDI {selectedTooth}</span>
        <span className={metrics.maxPocket !== null && metrics.maxPocket >= 6 ? "rounded-full bg-destructive/10 px-3 py-1 text-destructive" : "rounded-full bg-primary/10 px-3 py-1 text-primary"}>
          Pocket: {metrics.maxPocket === null ? "—" : `${metrics.maxPocket}mm`}
        </span>
      </div>
    </Card>
  );
}

function AnatomicalDentalArch({ toothVisuals, selectedTooth, onSelect }: {
  toothVisuals: PerioToothVisual[];
  selectedTooth: number | null;
  onSelect?: (tooth: number) => void;
}) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const [markerPositions, setMarkerPositions] = useState<Array<{ tooth: number; left: number; top: number }>>([]);
  const teethWithData = toothVisuals.map((item) => item.tooth);
  const conditions = buildPerioConditions(toothVisuals, selectedTooth);

  useLayoutEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const updateMarkerPositions = () => {
      const chartBounds = chart.getBoundingClientRect();
      const next = toothVisuals.flatMap((visual) => {
        if (!(visual.mobilityGrade && visual.mobilityGrade > 0) && !(visual.furcationGrade && visual.furcationGrade > 0)) return [];
        const tooth = chart.querySelector<HTMLElement>(`[role="option"][aria-label="Tooth ${visual.tooth}"]`);
        if (!tooth) return [];
        const bounds = tooth.getBoundingClientRect();
        return [{
          tooth: visual.tooth,
          left: bounds.left - chartBounds.left + bounds.width / 2,
          top: bounds.top - chartBounds.top + 2,
        }];
      });
      setMarkerPositions(next);
    };

    const frame = window.requestAnimationFrame(updateMarkerPositions);
    const settleTimer = window.setTimeout(updateMarkerPositions, 150);
    const observer = new ResizeObserver(updateMarkerPositions);
    observer.observe(chart);
    window.addEventListener("resize", updateMarkerPositions);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(settleTimer);
      observer.disconnect();
      window.removeEventListener("resize", updateMarkerPositions);
    };
  }, [selectedTooth, toothVisuals]);

  function handleChange(selected: ToothDetail[]) {
    const fdi = Number(selected.at(-1)?.notations.fdi);
    if (onSelect && teethWithData.includes(fdi)) onSelect(fdi);
  }

  return (
    <div ref={chartRef} className="relative min-h-[430px] overflow-hidden rounded-xl border border-border bg-card px-4 py-6 md:min-h-[500px] md:px-8">
      <div className="pointer-events-none absolute left-4 top-4 z-10 rounded-full bg-background/90 px-3 py-1 text-[10px] font-semibold uppercase text-muted-foreground">Sağ</div>
      <div className="pointer-events-none absolute right-4 top-4 z-10 rounded-full bg-background/90 px-3 py-1 text-[10px] font-semibold uppercase text-muted-foreground">Sol</div>
      <div className="mx-auto flex min-h-[390px] max-w-4xl items-center justify-center md:min-h-[450px]">
        <Odontogram
          key={selectedTooth ?? "empty"}
          defaultSelected={selectedTooth ? [`teeth-${selectedTooth}`] : []}
          singleSelect
          onChange={handleChange}
          notation="FDI"
          teethConditions={conditions}
          selectedColor="var(--primary)"
          hoverColor="var(--ring)"
          colors={{ darkBlue: "var(--primary)", baseBlue: "var(--ring)", lightBlue: "var(--secondary)" }}
          showTooltip
          tooltip={{
            content: (tooth) => tooth ? formatPerioToothTooltip(toothVisuals.find((item) => item.tooth === Number(tooth.notations.fdi))) : null,
          }}
          showLabels={false}
          layout="circle"
          className="perio-anatomical-arch"
          styles={{ width: "100%", maxWidth: "900px" }}
        />
      </div>
      {markerPositions.map((position) => {
        const visual = toothVisuals.find((item) => item.tooth === position.tooth);
        if (!visual) return null;
        return (
          <div
            key={position.tooth}
            className="pointer-events-none absolute z-20 flex -translate-x-1/2 -translate-y-full items-center gap-1 rounded-full border border-border bg-card/90 px-1.5 py-1 shadow-sm"
            style={{ left: position.left, top: position.top }}
            aria-label={formatPerioToothTooltip(visual)}
          >
            {visual.mobilityGrade !== null && visual.mobilityGrade > 0 ? (
              <span className="size-2.5 rounded-full bg-primary" title={`Mobilite ${visual.mobilityGrade}`} />
            ) : null}
            {visual.furcationGrade !== null && visual.furcationGrade > 0 ? (
              <span
                className="h-0 w-0 border-x-[5px] border-b-[9px] border-x-transparent border-b-amber-500"
                title={`Furkasyon ${visual.furcationGrade}`}
              />
            ) : null}
          </div>
        );
      })}
      <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
        <span className="rounded-full border border-border bg-card/90 px-3 py-1 text-xs font-medium text-muted-foreground shadow-sm">
          Anatomik FDI görünümü · ölçüm bulunan dişler seçilebilir
        </span>
      </div>
    </div>
  );
}

function buildPerioConditions(toothVisuals: PerioToothVisual[], selectedTooth: number | null): ToothConditionGroup[] {
  const groups = [
    { label: "Normal (0-3 mm)", fillColor: "var(--secondary)", outlineColor: "var(--ring)", matches: (value: number) => value <= 3 },
    { label: "Dikkat (4-5 mm)", fillColor: "var(--warning)", outlineColor: "var(--warning)", matches: (value: number) => value >= 4 && value <= 5 },
    { label: "Ciddi (6+ mm)", fillColor: "color-mix(in srgb, var(--destructive) 16%, var(--card))", outlineColor: "var(--destructive)", matches: (value: number) => value >= 6 },
  ];
  const conditions = groups.flatMap((group): ToothConditionGroup[] => {
    const teeth = toothVisuals.filter((item) => item.maxPocket !== null && group.matches(item.maxPocket)).map((item) => `teeth-${item.tooth}`);
    return teeth.length ? [{ label: group.label, teeth, fillColor: group.fillColor, outlineColor: group.outlineColor }] : [];
  });
  const selected = toothVisuals.find((item) => item.tooth === selectedTooth);
  if (selected) {
    const severity = groups.find((group) => selected.maxPocket !== null && group.matches(selected.maxPocket));
    conditions.push({
      label: "Aktif diş",
      teeth: [`teeth-${selected.tooth}`],
      fillColor: severity?.fillColor ?? "var(--card)",
      outlineColor: "var(--primary)",
    });
  }
  return conditions;
}

function formatPerioToothTooltip(visual: PerioToothVisual | undefined) {
  if (!visual) return "Ölçüm bulunmuyor";
  const details = [
    `FDI ${visual.tooth}`,
    `En derin cep: ${visual.maxPocket === null ? "—" : `${visual.maxPocket}mm`}`,
  ];
  if (visual.mobilityGrade !== null) details.push(`Mobilite: ${visual.mobilityGrade}`);
  if (visual.furcationGrade !== null) {
    details.push(`Furkasyon: ${visual.furcationGrade}${visual.furcationSite ? ` (${formatSite(visual.furcationSite)})` : ""}`);
  }
  return details.join(" · ");
}

function FocusedToothCard({ tooth, bySite, metrics, summary, uncertainItems }: {
  tooth: number;
  bySite: Map<PerioSite, PerioMeasurement>;
  metrics: ToothMetrics;
  summary: ToothPerioSummary | null;
  uncertainItems: string[];
}) {
  return (
    <Card className="gap-0 border-l-4 border-l-primary p-5 py-5 md:p-6">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-heading text-2xl font-semibold text-foreground">Tooth #{tooth}</h3>
          <p className="mt-1 text-xs font-medium text-muted-foreground">{toothLabel(tooth)}</p>
        </div>
        <span className={metrics.maxPocket !== null && metrics.maxPocket >= 6 ? "rounded bg-destructive/10 px-3 py-1 text-xs font-bold text-destructive" : "rounded bg-primary/10 px-3 py-1 text-xs font-bold text-primary"}>
          Pocket: {metrics.maxPocket === null ? "—" : `${metrics.maxPocket}mm`}
        </span>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <SurfaceGroup title="Buccal" sites={BUCCAL_SITES} bySite={bySite} />
        <SurfaceGroup title="Lingual" sites={LINGUAL_SITES} bySite={bySite} />
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
        <div className="flex flex-wrap gap-4">
          <BooleanMarker tone="error" label="BOP" value={metrics.hasBleeding} />
          <BooleanMarker tone="warning" label="Plak" value={metrics.hasPlaque} />
        </div>
        <span className="text-sm font-medium tabular-nums text-muted-foreground">
          REC: {metrics.maxRecession === null ? "—" : `${metrics.maxRecession}mm`} · CAL: {metrics.maxCal === null ? "—" : `${metrics.maxCal}mm`}
        </span>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <SummaryValue label="Mobilite" value={summary?.mobility_grade ?? null} uncertain={isSummaryUncertain(uncertainItems, tooth, "mobilite")} />
        <SummaryValue
          label="Furkasyon"
          value={summary?.furcation_grade == null ? null : `Grade ${summary.furcation_grade}${summary.furcation_site ? ` · ${formatSite(summary.furcation_site)}` : ""}`}
          uncertain={isSummaryUncertain(uncertainItems, tooth, "furkasyon")}
        />
      </div>
    </Card>
  );
}

function ComparisonToothCard({ tooth, measurements }: { tooth: number | null; measurements: PerioMeasurement[] }) {
  const bySite = new Map(measurements.map((item) => [item.site, item]));
  return (
    <Card className="gap-0 p-5 py-5 opacity-75 md:p-6">
      <div className="mb-5">
        <h3 className="font-heading text-2xl font-semibold text-foreground">{tooth ? `Tooth #${tooth}` : "Tooth #—"}</h3>
        <p className="mt-1 text-xs font-medium text-muted-foreground">{tooth ? toothLabel(tooth) : "Karşılaştırma için ikinci diş yok"}</p>
      </div>
      <div className="space-y-2">
        <div className="grid grid-cols-3 gap-1">
          {BUCCAL_SITES.map((site) => <MeasurementTile key={site} item={bySite.get(site)} value={bySite.get(site)?.pocket_depth_mm ?? null} compact />)}
        </div>
        <div className="grid grid-cols-3 gap-1">
          {LINGUAL_SITES.map((site) => <MeasurementTile key={site} item={bySite.get(site)} value={bySite.get(site)?.pocket_depth_mm ?? null} compact />)}
        </div>
      </div>
    </Card>
  );
}

function SurfaceGroup({ title, sites, bySite }: { title: string; sites: PerioSite[]; bySite: Map<PerioSite, PerioMeasurement> }) {
  return (
    <div className="space-y-3">
      <span className="text-xs font-bold uppercase text-muted-foreground">{title}</span>
      <div className="grid h-12 grid-cols-3 gap-1">
        {sites.map((site) => {
          const item = bySite.get(site);
          return <MeasurementTile key={site} item={item} value={item?.pocket_depth_mm ?? null} />;
        })}
      </div>
      <div className="grid grid-cols-3 gap-1 text-center text-[10px] font-semibold text-muted-foreground/70">
        {sites.map((site) => <span key={site}>{site}</span>)}
      </div>
    </div>
  );
}

function MeasurementTile({ item, value, compact = false }: { item: PerioMeasurement | undefined; value: number | null; compact?: boolean }) {
  const content = (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className={`flex items-center justify-center rounded text-sm font-medium tabular-nums ${compact ? "h-10" : "h-12"} ${measurementCellClass(item, value, true)}`}
    >
      {value === null ? <span className="text-muted-foreground/55">—</span> : value}
    </motion.div>
  );
  if (!item?.source_quote) return content;
  return (
    <Tooltip>
      <TooltipTrigger render={content} />
      <TooltipContent className="max-w-sm">Kaynak: {item.source_quote}</TooltipContent>
    </Tooltip>
  );
}

function BooleanMarker({ label, value, tone }: { label: string; value: boolean | null; tone: "error" | "warning" }) {
  const color = tone === "error" ? "bg-destructive" : "bg-amber-400";
  return (
    <div className="flex items-center gap-1.5">
      <span className={`size-2.5 rounded-full ${value === true ? color : "bg-muted"}`} />
      <span className="text-xs font-medium text-foreground">{label} {value === null ? "(—)" : value ? "(+)" : "(-)"}</span>
    </div>
  );
}

function GingivalLevelAnalysis({ teeth, selectedTooth, measurements }: {
  teeth: number[];
  selectedTooth: number;
  measurements: PerioMeasurement[];
}) {
  const chartTeeth = teeth.length ? teeth.slice(0, 6) : [selectedTooth];
  const points = chartTeeth.map((tooth, index) => {
    const toothMeasurements = measurements.filter((item) => item.tooth_number_fdi === tooth);
    const recession = maxNumber(toothMeasurements.map((item) => item.recession_mm ?? item.gingival_margin_mm));
    const x = chartTeeth.length === 1 ? 400 : (index / (chartTeeth.length - 1)) * 760 + 20;
    const y = 38 + Math.min((recession ?? 0) * 12, 44);
    return { tooth, recession, x, y };
  });
  const path = points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x},${point.y}`).join(" ");

  return (
    <Card className="gap-0 p-5 py-5 md:p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Waves className="size-5 text-destructive" />
          <h3 className="font-heading text-lg font-semibold uppercase text-foreground">Gingival Level Analysis</h3>
        </div>
        <div className="flex flex-wrap gap-4 text-xs font-medium text-muted-foreground">
          <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-destructive" /> Gingival Margin</span>
          <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-primary/20" /> CEJ Reference</span>
        </div>
      </div>
      <div className="relative h-48 rounded-xl border border-border bg-background/60 p-4">
        <div className="mb-2 flex justify-between px-4">
          {chartTeeth.map((tooth) => (
            <span key={tooth} className={`text-xs font-bold ${tooth === selectedTooth ? "text-primary" : "text-foreground"}`}>#{tooth}</span>
          ))}
        </div>
        <svg className="h-32 w-full" preserveAspectRatio="none" viewBox="0 0 800 100">
          <path d="M 0,20 L 800,20" fill="none" stroke="var(--ring)" strokeDasharray="4 4" strokeOpacity="0.2" strokeWidth="1" />
          <path d={path || "M 0,40 L 800,40"} fill="none" stroke="var(--destructive)" strokeWidth="2" />
          {points.map((point) => (
            <g key={point.tooth} transform={`translate(${point.x - 10}, ${point.y})`}>
              <circle cx="10" cy="0" r="3" fill="var(--destructive)" />
              <text x="10" y="15" fill="var(--destructive)" fontFamily="Inter" fontSize="10" fontWeight="700" textAnchor="middle">
                {point.recession === null ? "—" : `${point.recession}mm`}
              </text>
            </g>
          ))}
        </svg>
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 text-center text-xs italic text-muted-foreground">
          CEJ referansına göre dikte edilen resesyon derinlikleri
        </div>
      </div>
    </Card>
  );
}

function ClinicalRefinementSidebar({ metrics, selectedTooth, summary, uncertainItems, sourceQuotes }: {
  metrics: ToothMetrics;
  selectedTooth: number;
  summary: ToothPerioSummary | null;
  uncertainItems: string[];
  sourceQuotes: PerioMeasurement[];
}) {
  return (
    <Card className="space-y-5 p-5 py-5">
      <div className="grid grid-cols-2 gap-4">
        <MetricCard label="Kritik Diş" value={metrics.maxPocket !== null && metrics.maxPocket >= 6 ? "1" : "—"} tone="primary" />
        <MetricCard label="BOP" value={metrics.hasBleeding === null ? "—" : metrics.hasBleeding ? "+" : "-"} tone="error" />
      </div>

      <Card size="sm" className="gap-0 bg-card/55 p-4 py-4">
        <div className="mb-4 flex items-center gap-2">
          <ClipboardCheck className="size-5 text-primary" />
          <h3 className="font-heading text-lg font-semibold text-foreground">Klinik Protokol</h3>
        </div>
        <div className="space-y-3">
          <ProtocolRow label="Mobilite" value={summary?.mobility_grade ?? null} />
          <ProtocolRow label="Furkasyon" value={summary?.furcation_grade == null ? null : `Grade ${summary.furcation_grade}`} />
          <ProtocolRow label="Aktif Diş" value={`FDI ${selectedTooth}`} />
        </div>
      </Card>

      <section className="space-y-3">
        <h4 className="px-1 text-xs font-bold uppercase text-muted-foreground">Klinik Kontrol Gerekli</h4>
        {uncertainItems.length ? (
          uncertainItems.slice(0, 3).map((item, index) => (
            <Card key={`${item}-${index}`} size="sm" className="flex-row gap-3 border-destructive/20 bg-destructive/10 p-4 py-4">
              <AlertTriangle className="mt-0.5 size-5 shrink-0 text-destructive" />
              <p className="text-sm font-medium text-foreground">{item}</p>
            </Card>
          ))
        ) : (
          <Card size="sm" className="flex-row gap-3 bg-secondary p-4 py-4 text-muted-foreground">
            <CheckCircle2 className="mt-0.5 size-5 shrink-0" />
            <p className="text-sm">Belirsiz perio öğesi bildirilmedi.</p>
          </Card>
        )}
      </section>

      <Card size="sm" className="gap-0 border-primary/20 bg-primary/5 p-4 py-4">
        <h3 className="mb-3 text-xs font-bold uppercase text-primary">Kaynak Alıntısı</h3>
        <div className="space-y-4">
          {sourceQuotes.length ? (
            sourceQuotes.map((item, index) => (
              <div key={`${item.site}-${index}`} className={`flex gap-3 ${index > 0 ? "opacity-65" : ""}`}>
                <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
                  <Play className="size-4 fill-current" />
                </div>
                <div>
                  <p className="text-sm italic text-muted-foreground">"{item.source_quote}"</p>
                  <span className="mt-1 inline-block text-xs font-bold text-primary">FDI {item.tooth_number_fdi} · {item.site}</span>
                </div>
              </div>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">—</p>
          )}
        </div>
      </Card>
    </Card>
  );
}

function MetricCard({ label, value, tone }: { label: string; value: string; tone: "primary" | "error" }) {
  const styles = tone === "primary"
    ? "border-primary/10 bg-primary/5 text-primary"
    : "border-destructive/10 bg-destructive/5 text-destructive";
  return (
    <Card size="sm" className={`gap-0 p-4 py-4 ${styles}`}>
      <span className="mb-1 block text-xs font-bold uppercase">{label}</span>
      <span className="font-heading text-2xl font-semibold tabular-nums">{value}</span>
    </Card>
  );
}

function ProtocolRow({ label, value }: { label: string; value: number | string | null }) {
  return (
    <Card size="sm" className="flex-row items-center justify-between gap-3 bg-card/65 p-3 py-3">
      <span className="font-semibold text-foreground">{label}</span>
      <span className="text-sm italic text-muted-foreground">{value ?? "—"}</span>
    </Card>
  );
}

function SummaryValue({ label, value, uncertain }: { label: string; value: number | string | null; uncertain: boolean }) {
  return (
    <Card size="sm" className={`gap-0 p-3 py-3 ${uncertain ? "border-amber-200 bg-amber-50" : "bg-card/60"}`}>
      <p className="text-xs font-semibold uppercase text-muted-foreground">{label}</p>
      <p className="mt-1 font-heading text-lg font-semibold tabular-nums text-foreground">{value ?? "—"}</p>
    </Card>
  );
}

function BlankMeasurementCell({ label }: { label: string }) {
  return (
    <div className="flex h-12 flex-col items-center justify-center rounded bg-muted/50 text-xs font-semibold text-muted-foreground/60">
      <span>—</span>
      <span className="text-[10px]">{label}</span>
    </div>
  );
}

function EmptySidebarRow({ label }: { label: string }) {
  return (
    <Card size="sm" className="flex-row items-center justify-between gap-3 bg-card/55 p-3 py-3">
      <span className="text-sm font-semibold text-foreground">{label}</span>
      <span className="text-sm text-muted-foreground">—</span>
    </Card>
  );
}

type ToothMetrics = {
  maxPocket: number | null;
  maxRecession: number | null;
  maxCal: number | null;
  hasBleeding: boolean | null;
  hasPlaque: boolean | null;
};

function getToothMetrics(measurements: PerioMeasurement[]): ToothMetrics {
  const maxPocket = maxNumber(measurements.map((item) => item.pocket_depth_mm));
  const maxRecession = maxNumber(measurements.map((item) => item.recession_mm));
  const maxCal = maxNumber(measurements.map((item) => {
    if (item.pocket_depth_mm === null && item.recession_mm === null) return null;
    return (item.pocket_depth_mm ?? 0) + (item.recession_mm ?? 0);
  }));
  return {
    maxPocket,
    maxRecession,
    maxCal,
    hasBleeding: aggregateBoolean(measurements.map((item) => item.bleeding_on_probing)),
    hasPlaque: aggregateBoolean(measurements.map((item) => item.plaque)),
  };
}

function maxNumber(values: Array<number | null | undefined>) {
  const numeric = values.filter((value): value is number => typeof value === "number");
  return numeric.length ? Math.max(...numeric) : null;
}

function aggregateBoolean(values: Array<boolean | null>) {
  if (values.some((value) => value === true)) return true;
  if (values.some((value) => value === false)) return false;
  return null;
}

function measurementCellClass(item: PerioMeasurement | undefined, value: number | string | boolean | null, heatmap = false) {
  if (item?.is_uncertain) return "bg-amber-50 text-amber-950";
  if (!heatmap || typeof value !== "number") return "bg-muted/50 text-foreground";
  if (value >= 6) return "bg-destructive/10 font-bold italic text-destructive underline";
  if (value >= 4) return "bg-amber-50 font-semibold text-amber-950";
  return "bg-muted/50 text-foreground";
}

function isSummaryUncertain(items: string[], tooth: number, term: string) {
  return items.some((item) => {
    const normalized = item.toLocaleLowerCase("tr-TR");
    return normalized.includes(term) && (normalized.includes(String(tooth)) || !/\d{2}/.test(normalized));
  });
}

function toothLabel(tooth: number) {
  const quadrant = Math.floor(tooth / 10);
  const position = tooth % 10;
  const arch = quadrant === 1 || quadrant === 2 ? "Upper" : "Lower";
  const side = quadrant === 1 || quadrant === 4 ? "Right" : "Left";
  const kind = position >= 6 ? "Molar" : position >= 4 ? "Premolar" : position === 3 ? "Canine" : "Anterior";
  return `${kind} - ${arch} ${side}`;
}

function formatSite(site: string) {
  const labels: Record<string, string> = { buccal: "Bukkal", lingual: "Lingual", palatal: "Palatinal", mesial: "Mezial", distal: "Distal" };
  return labels[site] ?? site;
}
