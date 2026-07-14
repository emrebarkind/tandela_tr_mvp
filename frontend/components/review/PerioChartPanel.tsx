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
    <div className="space-y-5 font-body text-[#161d19]">
      <section className="overflow-hidden rounded-2xl border border-[#c0c9c1]/60 bg-white shadow-card">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-[#c0c9c1]/50 px-6 py-5 lg:px-8">
          <div className="flex items-center gap-4">
            <div className="flex size-11 items-center justify-center rounded-xl bg-[#e8f0e8] text-[#4A7C63]">
              <Waves className="size-5" />
            </div>
            <div>
              <h2 className="font-heading text-xl font-semibold">Periodontal Çizelgeleme</h2>
              <p className="mt-1 text-sm text-[#404943]">Altı nokta ölçümlerinden incelemeye hazır taslak</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Badge className="rounded-full bg-[#e8f0e8] px-3 py-1 text-xs font-semibold text-[#404943] hover:bg-[#e8f0e8]">
              Taslak · Hekim onayı gereklidir
            </Badge>
            <span className="flex items-center gap-2 text-xs font-semibold text-[#404943]">
              <span className={`size-2 rounded-full ${result ? "bg-[#4A7C63]" : "bg-[#c0c9c1]"}`} />
              {result ? "Analiz hazır" : "Dikte bekleniyor"}
            </span>
          </div>
        </header>

        <div className="grid gap-5 bg-[#F8F9F7] p-5 lg:grid-cols-[minmax(0,1fr)_240px] lg:p-6">
          <div className="relative">
            <Mic className="pointer-events-none absolute left-4 top-4 size-4 text-[#4A7C63]" />
            <Textarea
              ref={dictationRef}
              value={dictation}
              onChange={(event) => setDictation(event.target.value)}
              placeholder="Örn. 16 bukkal üç dört dört, kanama yok, plak var. Mobilite bir, furkasyon iki bukkal."
              className="min-h-32 resize-y rounded-xl border-[#c0c9c1] bg-white py-4 pl-11 pr-4 text-sm leading-6 shadow-none placeholder:text-[#404943]/60 focus-visible:ring-[#4A7C63]"
            />
          </div>
          <div className="flex flex-col justify-between gap-4">
            <p className="text-sm leading-6 text-[#404943]">Yalnızca açıkça dikte edilen ölçümler eklenir. Belirsiz alanlar boş bırakılır.</p>
            <Button
              type="button"
              onClick={() => void analyze()}
              disabled={isLoading || !dictation.trim()}
              className="h-11 rounded-xl bg-[#4A7C63] px-5 font-semibold text-white shadow-none hover:bg-[#4A7C63]/90"
            >
              {isLoading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Stethoscope className="mr-2 size-4" />}
              Analiz Et
            </Button>
          </div>
        </div>
      </section>

      {error ? <p className="rounded-xl border border-[#ba1a1a]/30 bg-[#ffdad6]/60 px-4 py-3 text-sm font-medium text-[#ba1a1a]">{error}</p> : null}

      {result && selectedTooth ? (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.28 }}
          className="space-y-5"
        >
          <section className="overflow-hidden rounded-2xl border border-[#c0c9c1]/60 bg-white shadow-card">
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#c0c9c1]/50 px-6 py-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-[#404943]">İncelenen diş</p>
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
                        ? "border-[#4A7C63] bg-[#4A7C63] text-white"
                        : "border-[#c0c9c1] bg-white text-[#404943] hover:bg-[#e8f0e8]"
                    }`}
                  >
                    {tooth}
                  </button>
                ))}
              </div>
            </div>
            <div className="bg-[#F8F9F7] p-4 md:p-6">
              <AnatomicalDentalArch toothVisuals={toothVisuals} selectedTooth={selectedTooth} onSelect={setSelectedTooth} />
            </div>
          </section>

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
        <div className="rounded-2xl border border-amber-200 bg-amber-50/95 p-4 text-amber-950 shadow-panel backdrop-blur-md">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="mb-2 flex items-center gap-2 font-heading font-semibold">
                <AlertTriangle className="size-4" />
                Kontrol Edilmeli
              </div>
              <ul className="space-y-1 text-sm">{result.uncertain_items.map((item, index) => <li key={`${item}-${index}`}>• {item}</li>)}</ul>
            </div>
            <Button variant="outline" className="rounded-full border-amber-300 bg-white" onClick={() => dictationRef.current?.focus()}>
              Hemen Düzelt
            </Button>
          </div>
        </div>
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
    <section className="overflow-hidden rounded-2xl border border-[#c0c9c1]/60 bg-white shadow-card">
      <div className="flex items-center justify-between border-b border-[#c0c9c1]/50 px-6 py-5">
        <div>
          <h3 className="font-heading text-lg font-semibold">Periodontal ölçümler</h3>
          <p className="mt-1 text-sm text-[#404943]">FDI {tooth} · altı nokta görünümü</p>
        </div>
        <Badge className="rounded-full bg-[#e7fef8] text-[#4A7C63] hover:bg-[#e7fef8]">Taslak</Badge>
      </div>

      <div className="overflow-x-auto p-4 md:p-6">
        <table className="w-full min-w-[640px] border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              <th className="w-40 border-b border-[#c0c9c1]/60 px-3 py-3 text-left text-xs font-semibold uppercase text-[#404943]">Ölçüm</th>
              {SITE_ORDER.map((site, index) => (
                <th key={site} className={`border-b border-[#c0c9c1]/60 px-3 py-3 text-center font-semibold ${index === 3 ? "border-l" : ""}`}>
                  <span className="block font-heading text-base">{site}</span>
                  <span className="mt-0.5 block text-[10px] font-normal text-[#404943]">{index < 3 ? "Bukkal" : "Lingual"}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {MEASUREMENT_ROWS.map((row) => (
              <tr key={row.field}>
                <th className="border-b border-[#c0c9c1]/35 px-3 py-4 text-left font-medium text-[#404943]">{row.label}</th>
                {SITE_ORDER.map((site, index) => {
                  const item = bySite.get(site);
                  const value = item?.[row.field] ?? null;
                  return (
                    <td key={site} className={`border-b border-[#c0c9c1]/35 p-1.5 text-center ${index === 3 ? "border-l" : ""}`}>
                      <PerioTableCell item={item} value={value} suffix={"suffix" in row ? row.suffix : undefined} heatmap={"heatmap" in row && row.heatmap} />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-[#404943]">
          <span className="flex items-center gap-2"><span className="size-2 rounded-full bg-[#e8f0e8]" /> 0–3 mm</span>
          <span className="flex items-center gap-2"><span className="size-2 rounded-full bg-amber-200" /> 4–5 mm / kontrol</span>
          <span className="flex items-center gap-2"><span className="size-2 rounded-full bg-[#ffdad6]" /> 6+ mm</span>
        </div>
      </div>
    </section>
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
    <aside className="rounded-2xl border border-[#c0c9c1]/60 bg-white p-5 shadow-card">
      <div className="flex items-center gap-3 border-b border-[#c0c9c1]/40 pb-4">
        <div className="flex size-10 items-center justify-center rounded-xl bg-[#e8f0e8] text-[#4A7C63]"><ClipboardCheck className="size-5" /></div>
        <div>
          <h3 className="font-heading font-semibold">Diş özeti</h3>
          <p className="text-xs text-[#404943]">FDI {tooth}</p>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <SummaryValue label="En derin cep" value={metrics.maxPocket === null ? null : `${metrics.maxPocket} mm`} uncertain={false} />
        <SummaryValue label="Resesyon" value={metrics.maxRecession === null ? null : `${metrics.maxRecession} mm`} uncertain={false} />
        <SummaryValue label="Mobilite" value={summary?.mobility_grade ?? null} uncertain={isSummaryUncertain(uncertainItems, tooth, "mobilite")} />
        <SummaryValue label="Furkasyon" value={summary?.furcation_grade == null ? null : `${summary.furcation_grade}${summary.furcation_site ? ` · ${formatSite(summary.furcation_site)}` : ""}`} uncertain={isSummaryUncertain(uncertainItems, tooth, "furkasyon")} />
      </div>
      <div className="mt-4 flex gap-4 rounded-xl bg-[#F8F9F7] p-3">
        <BooleanMarker tone="error" label="Kanama" value={metrics.hasBleeding} />
        <BooleanMarker tone="warning" label="Plak" value={metrics.hasPlaque} />
      </div>
      <div className="mt-5">
        <p className="text-xs font-semibold uppercase text-[#404943]">Kaynak</p>
        <div className="mt-2 space-y-2">
          {sourceQuotes.length ? sourceQuotes.map((item, index) => (
            <p key={`${item.site}-${index}`} className="rounded-xl border border-[#c0c9c1]/35 bg-[#F8F9F7] p-3 text-sm italic leading-5 text-[#404943]">
              “{item.source_quote}”
            </p>
          )) : <p className="text-sm text-[#404943]">—</p>}
        </div>
      </div>
    </aside>
  );
}

function EmptyPerioState() {
  return (
    <section className="overflow-hidden rounded-2xl border border-[#c0c9c1]/60 bg-white shadow-card">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#c0c9c1]/50 px-6 py-5">
        <div>
          <h3 className="font-heading text-lg font-semibold">Periodontal taslak</h3>
          <p className="mt-1 text-sm text-[#404943]">Dikte analiz edildiğinde ölçüm bulunan dişler burada işaretlenir.</p>
        </div>
        <span className="rounded-full bg-[#e8f0e8] px-3 py-1 text-xs font-semibold text-[#404943]">FDI görünümü</span>
      </div>

      <div className="grid gap-6 bg-[#F8F9F7] p-5 xl:grid-cols-[minmax(0,1fr)_300px] xl:p-6">
        <div className="space-y-5">
          <div className="rounded-xl border border-[#c0c9c1]/45 bg-white p-4">
            <div className="mb-3 flex items-center justify-between text-xs font-semibold uppercase text-[#404943]">
              <span>Sağ</span>
              <span>Tam diş arkı</span>
              <span>Sol</span>
            </div>
            <AnatomicalDentalArch toothVisuals={[]} selectedTooth={null} />
          </div>

          <div className="overflow-x-auto rounded-xl border border-[#c0c9c1]/45 bg-white p-4">
            <div className="min-w-[620px]">
              <div className="grid grid-cols-[160px_repeat(6,minmax(64px,1fr))] border-b border-[#c0c9c1]/50 text-center text-xs font-semibold text-[#404943]">
                <span className="px-3 py-3 text-left">Ölçüm</span>
                {SITE_ORDER.map((site) => <span key={site} className="px-2 py-3">{site}</span>)}
              </div>
              {MEASUREMENT_ROWS.map((row) => (
                <div key={row.field} className="grid grid-cols-[160px_repeat(6,minmax(64px,1fr))] border-b border-[#c0c9c1]/30 last:border-0">
                  <span className="px-3 py-4 text-sm font-medium text-[#404943]">{row.label}</span>
                  {SITE_ORDER.map((site) => <BlankMeasurementCell key={`${row.field}-${site}`} label="" />)}
                </div>
              ))}
            </div>
          </div>
        </div>

        <aside className="rounded-xl border border-[#c0c9c1]/45 bg-white p-5">
          <div className="flex size-10 items-center justify-center rounded-xl bg-[#e8f0e8] text-[#4A7C63]">
            <ClipboardCheck className="size-5" />
          </div>
          <h3 className="mt-4 font-heading text-lg font-semibold">Klinik kontrol</h3>
          <p className="mt-2 text-sm leading-6 text-[#404943]">Ölçümler yalnızca açık dikteye göre doldurulur. Söylenmeyen alanlar boş kalır.</p>
          <div className="mt-5 space-y-2">
            <EmptySidebarRow label="Mobilite" />
            <EmptySidebarRow label="Furkasyon" />
            <EmptySidebarRow label="Kaynak alıntısı" />
          </div>
        </aside>
      </div>
    </section>
  );
}

function DentalArchVisualizer({ teeth, selectedTooth, metrics, onSelect }: {
  teeth: number[];
  selectedTooth: number;
  metrics: ToothMetrics;
  onSelect: (tooth: number) => void;
}) {
  return (
    <section className="rounded-2xl border border-white/50 bg-white/70 p-5 shadow-panel backdrop-blur-md md:p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Stethoscope className="size-5 text-[#4A7C63]" />
          <h3 className="font-heading text-lg font-semibold uppercase text-[#161d19]">Full Dental Arch (FDI)</h3>
        </div>
        <div className="flex items-center gap-3 text-xs font-semibold uppercase text-[#404943]">
          <span>Sağ</span>
          <span className="h-3 w-px bg-[#c0c9c1]" />
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
      <div className="mt-4 flex flex-wrap items-center gap-3 text-xs font-medium text-[#404943]">
        <span className="rounded-full bg-[#e8f0e8] px-3 py-1">Aktif: FDI {selectedTooth}</span>
        <span className={metrics.maxPocket !== null && metrics.maxPocket >= 6 ? "rounded-full bg-[#ffdad6] px-3 py-1 text-[#ba1a1a]" : "rounded-full bg-[#e7fef8] px-3 py-1 text-[#4A7C63]"}>
          Pocket: {metrics.maxPocket === null ? "—" : `${metrics.maxPocket}mm`}
        </span>
      </div>
    </section>
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
    <div ref={chartRef} className="relative min-h-[430px] overflow-hidden rounded-xl border border-[#c0c9c1]/35 bg-white px-4 py-6 md:min-h-[500px] md:px-8">
      <div className="pointer-events-none absolute left-4 top-4 z-10 rounded-full bg-[#F8F9F7]/90 px-3 py-1 text-[10px] font-semibold uppercase text-[#404943]">Sağ</div>
      <div className="pointer-events-none absolute right-4 top-4 z-10 rounded-full bg-[#F8F9F7]/90 px-3 py-1 text-[10px] font-semibold uppercase text-[#404943]">Sol</div>
      <div className="mx-auto flex min-h-[390px] max-w-4xl items-center justify-center md:min-h-[450px]">
        <Odontogram
          key={selectedTooth ?? "empty"}
          defaultSelected={selectedTooth ? [`teeth-${selectedTooth}`] : []}
          singleSelect
          onChange={handleChange}
          notation="FDI"
          teethConditions={conditions}
          selectedColor="#2D5A45"
          hoverColor="#4A7C63"
          colors={{ darkBlue: "#2D5A45", baseBlue: "#4A7C63", lightBlue: "#bceed2" }}
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
            className="pointer-events-none absolute z-20 flex -translate-x-1/2 -translate-y-full items-center gap-1 rounded-full border border-white/80 bg-white/90 px-1.5 py-1 shadow-sm"
            style={{ left: position.left, top: position.top }}
            aria-label={formatPerioToothTooltip(visual)}
          >
            {visual.mobilityGrade !== null && visual.mobilityGrade > 0 ? (
              <span className="size-2.5 rounded-full bg-[#4A7C63]" title={`Mobilite ${visual.mobilityGrade}`} />
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
        <span className="rounded-full border border-[#c0c9c1]/50 bg-white/90 px-3 py-1 text-xs font-medium text-[#404943] shadow-sm">
          Anatomik FDI görünümü · ölçüm bulunan dişler seçilebilir
        </span>
      </div>
    </div>
  );
}

function buildPerioConditions(toothVisuals: PerioToothVisual[], selectedTooth: number | null): ToothConditionGroup[] {
  const groups = [
    { label: "Normal (0-3 mm)", fillColor: "#e8f0e8", outlineColor: "#4A7C63", matches: (value: number) => value <= 3 },
    { label: "Dikkat (4-5 mm)", fillColor: "#E49545", outlineColor: "#E49545", matches: (value: number) => value >= 4 && value <= 5 },
    { label: "Ciddi (6+ mm)", fillColor: "#ffdad6", outlineColor: "#ba1a1a", matches: (value: number) => value >= 6 },
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
      fillColor: severity?.fillColor ?? "#ffffff",
      outlineColor: "#2D5A45",
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
    <section className="rounded-2xl border border-[#c0c9c1]/60 border-l-4 border-l-[#4A7C63] bg-white/75 p-5 shadow-card backdrop-blur-md md:p-6">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-heading text-2xl font-semibold text-[#161d19]">Tooth #{tooth}</h3>
          <p className="mt-1 text-xs font-medium text-[#404943]">{toothLabel(tooth)}</p>
        </div>
        <span className={metrics.maxPocket !== null && metrics.maxPocket >= 6 ? "rounded bg-[#ffdad6] px-3 py-1 text-xs font-bold text-[#ba1a1a]" : "rounded bg-[#e7fef8] px-3 py-1 text-xs font-bold text-[#4A7C63]"}>
          Pocket: {metrics.maxPocket === null ? "—" : `${metrics.maxPocket}mm`}
        </span>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <SurfaceGroup title="Buccal" sites={BUCCAL_SITES} bySite={bySite} />
        <SurfaceGroup title="Lingual" sites={LINGUAL_SITES} bySite={bySite} />
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-[#c0c9c1]/30 pt-4">
        <div className="flex flex-wrap gap-4">
          <BooleanMarker tone="error" label="BOP" value={metrics.hasBleeding} />
          <BooleanMarker tone="warning" label="Plak" value={metrics.hasPlaque} />
        </div>
        <span className="text-sm font-medium tabular-nums text-[#404943]">
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
    </section>
  );
}

function ComparisonToothCard({ tooth, measurements }: { tooth: number | null; measurements: PerioMeasurement[] }) {
  const bySite = new Map(measurements.map((item) => [item.site, item]));
  return (
    <section className="rounded-2xl border border-[#c0c9c1]/50 bg-white/45 p-5 opacity-75 shadow-card backdrop-blur-md md:p-6">
      <div className="mb-5">
        <h3 className="font-heading text-2xl font-semibold text-[#161d19]">{tooth ? `Tooth #${tooth}` : "Tooth #—"}</h3>
        <p className="mt-1 text-xs font-medium text-[#404943]">{tooth ? toothLabel(tooth) : "Karşılaştırma için ikinci diş yok"}</p>
      </div>
      <div className="space-y-2">
        <div className="grid grid-cols-3 gap-1">
          {BUCCAL_SITES.map((site) => <MeasurementTile key={site} item={bySite.get(site)} value={bySite.get(site)?.pocket_depth_mm ?? null} compact />)}
        </div>
        <div className="grid grid-cols-3 gap-1">
          {LINGUAL_SITES.map((site) => <MeasurementTile key={site} item={bySite.get(site)} value={bySite.get(site)?.pocket_depth_mm ?? null} compact />)}
        </div>
      </div>
    </section>
  );
}

function SurfaceGroup({ title, sites, bySite }: { title: string; sites: PerioSite[]; bySite: Map<PerioSite, PerioMeasurement> }) {
  return (
    <div className="space-y-3">
      <span className="text-xs font-bold uppercase text-[#404943]">{title}</span>
      <div className="grid h-12 grid-cols-3 gap-1">
        {sites.map((site) => {
          const item = bySite.get(site);
          return <MeasurementTile key={site} item={item} value={item?.pocket_depth_mm ?? null} />;
        })}
      </div>
      <div className="grid grid-cols-3 gap-1 text-center text-[10px] font-semibold text-[#404943]/70">
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
      {value === null ? <span className="text-[#404943]/55">—</span> : value}
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
  const color = tone === "error" ? "bg-[#ba1a1a]" : "bg-orange-400";
  return (
    <div className="flex items-center gap-1.5">
      <span className={`size-2.5 rounded-full ${value === true ? color : "bg-[#d4dcd5]"}`} />
      <span className="text-xs font-medium text-[#161d19]">{label} {value === null ? "(—)" : value ? "(+)" : "(-)"}</span>
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
    <section className="rounded-2xl border border-white/50 bg-white/70 p-5 shadow-panel backdrop-blur-md md:p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Waves className="size-5 text-[#ba1a1a]" />
          <h3 className="font-heading text-lg font-semibold uppercase text-[#161d19]">Gingival Level Analysis</h3>
        </div>
        <div className="flex flex-wrap gap-4 text-xs font-medium text-[#404943]">
          <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-[#ba1a1a]" /> Gingival Margin</span>
          <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-[#4A7C63]/20" /> CEJ Reference</span>
        </div>
      </div>
      <div className="relative h-48 rounded-xl border border-[#c0c9c1]/25 bg-[#F8F9F7]/60 p-4">
        <div className="mb-2 flex justify-between px-4">
          {chartTeeth.map((tooth) => (
            <span key={tooth} className={`text-xs font-bold ${tooth === selectedTooth ? "text-[#4A7C63]" : "text-[#161d19]"}`}>#{tooth}</span>
          ))}
        </div>
        <svg className="h-32 w-full" preserveAspectRatio="none" viewBox="0 0 800 100">
          <path d="M 0,20 L 800,20" fill="none" stroke="#4A7C63" strokeDasharray="4 4" strokeOpacity="0.2" strokeWidth="1" />
          <path d={path || "M 0,40 L 800,40"} fill="none" stroke="#ba1a1a" strokeWidth="2" />
          {points.map((point) => (
            <g key={point.tooth} transform={`translate(${point.x - 10}, ${point.y})`}>
              <circle cx="10" cy="0" r="3" fill="#ba1a1a" />
              <text x="10" y="15" fill="#ba1a1a" fontFamily="Inter" fontSize="10" fontWeight="700" textAnchor="middle">
                {point.recession === null ? "—" : `${point.recession}mm`}
              </text>
            </g>
          ))}
        </svg>
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 text-center text-xs italic text-[#404943]">
          CEJ referansına göre dikte edilen resesyon derinlikleri
        </div>
      </div>
    </section>
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
    <aside className="space-y-5 rounded-2xl border border-white/50 bg-white/70 p-5 shadow-panel backdrop-blur-md">
      <div className="grid grid-cols-2 gap-4">
        <MetricCard label="Kritik Diş" value={metrics.maxPocket !== null && metrics.maxPocket >= 6 ? "1" : "—"} tone="primary" />
        <MetricCard label="BOP" value={metrics.hasBleeding === null ? "—" : metrics.hasBleeding ? "+" : "-"} tone="error" />
      </div>

      <section className="rounded-2xl border border-[#c0c9c1]/60 bg-white/55 p-4">
        <div className="mb-4 flex items-center gap-2">
          <ClipboardCheck className="size-5 text-[#4A7C63]" />
          <h3 className="font-heading text-lg font-semibold text-[#161d19]">Klinik Protokol</h3>
        </div>
        <div className="space-y-3">
          <ProtocolRow label="Mobilite" value={summary?.mobility_grade ?? null} />
          <ProtocolRow label="Furkasyon" value={summary?.furcation_grade == null ? null : `Grade ${summary.furcation_grade}`} />
          <ProtocolRow label="Aktif Diş" value={`FDI ${selectedTooth}`} />
        </div>
      </section>

      <section className="space-y-3">
        <h4 className="px-1 text-xs font-bold uppercase text-[#404943]">Klinik Kontrol Gerekli</h4>
        {uncertainItems.length ? (
          uncertainItems.slice(0, 3).map((item, index) => (
            <div key={`${item}-${index}`} className="flex gap-3 rounded-2xl border border-[#ba1a1a]/20 bg-[#ffdad6]/30 p-4">
              <AlertTriangle className="mt-0.5 size-5 shrink-0 text-[#ba1a1a]" />
              <p className="text-sm font-medium text-[#161d19]">{item}</p>
            </div>
          ))
        ) : (
          <div className="flex gap-3 rounded-2xl bg-[#e8f0e8] p-4 text-[#404943]">
            <CheckCircle2 className="mt-0.5 size-5 shrink-0" />
            <p className="text-sm">Belirsiz perio öğesi bildirilmedi.</p>
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-[#4A7C63]/20 bg-[#e7fef8]/30 p-4">
        <h3 className="mb-3 text-xs font-bold uppercase text-[#4A7C63]">Kaynak Alıntısı</h3>
        <div className="space-y-4">
          {sourceQuotes.length ? (
            sourceQuotes.map((item, index) => (
              <div key={`${item.site}-${index}`} className={`flex gap-3 ${index > 0 ? "opacity-65" : ""}`}>
                <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-[#4A7C63] text-white">
                  <Play className="size-4 fill-current" />
                </div>
                <div>
                  <p className="text-sm italic text-[#404943]">"{item.source_quote}"</p>
                  <span className="mt-1 inline-block text-xs font-bold text-[#4A7C63]">FDI {item.tooth_number_fdi} · {item.site}</span>
                </div>
              </div>
            ))
          ) : (
            <p className="text-sm text-[#404943]">—</p>
          )}
        </div>
      </section>
    </aside>
  );
}

function MetricCard({ label, value, tone }: { label: string; value: string; tone: "primary" | "error" }) {
  const styles = tone === "primary"
    ? "border-[#4A7C63]/10 bg-[#4A7C63]/5 text-[#4A7C63]"
    : "border-[#ba1a1a]/10 bg-[#ba1a1a]/5 text-[#ba1a1a]";
  return (
    <div className={`rounded-2xl border p-4 ${styles}`}>
      <span className="mb-1 block text-xs font-bold uppercase">{label}</span>
      <span className="font-heading text-2xl font-semibold tabular-nums">{value}</span>
    </div>
  );
}

function ProtocolRow({ label, value }: { label: string; value: number | string | null }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-[#c0c9c1]/30 bg-white/65 p-3">
      <span className="font-semibold text-[#161d19]">{label}</span>
      <span className="text-sm italic text-[#404943]">{value ?? "—"}</span>
    </div>
  );
}

function SummaryValue({ label, value, uncertain }: { label: string; value: number | string | null; uncertain: boolean }) {
  return (
    <div className={`rounded-lg border p-3 ${uncertain ? "border-amber-200 bg-amber-50" : "border-[#c0c9c1]/45 bg-white/60"}`}>
      <p className="text-xs font-semibold uppercase text-[#404943]">{label}</p>
      <p className="mt-1 font-heading text-lg font-semibold tabular-nums text-[#161d19]">{value ?? "—"}</p>
    </div>
  );
}

function BlankMeasurementCell({ label }: { label: string }) {
  return (
    <div className="flex h-12 flex-col items-center justify-center rounded bg-[#d4dcd5]/30 text-xs font-semibold text-[#404943]/60">
      <span>—</span>
      <span className="text-[10px]">{label}</span>
    </div>
  );
}

function EmptySidebarRow({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-[#c0c9c1]/35 bg-white/55 p-3">
      <span className="text-sm font-semibold text-[#161d19]">{label}</span>
      <span className="text-sm text-[#404943]">—</span>
    </div>
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
  if (!heatmap || typeof value !== "number") return "bg-[#d4dcd5]/30 text-[#161d19]";
  if (value >= 6) return "bg-[#ffdad6]/55 font-bold italic text-[#ba1a1a] underline";
  if (value >= 4) return "bg-amber-50 font-semibold text-amber-950";
  return "bg-[#d4dcd5]/30 text-[#161d19]";
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
