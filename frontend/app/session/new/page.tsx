"use client";

import { useMemo, useRef, useState } from "react";
import { CheckCircle2, ClipboardCheck, Loader2, Mic, Save, ShieldCheck, Sparkles } from "lucide-react";
import { ApprovedExport } from "@/components/review/ApprovedExport";
import { CodeSuggestionsPanel } from "@/components/review/CodeSuggestionsPanel";
import { DentalChartPanel } from "@/components/review/DentalChartPanel";
import { LiveTranscriptRecorder } from "@/components/review/LiveTranscriptRecorder";
import { NoteDocument } from "@/components/review/NoteDocument";
import { RoleGate } from "@/components/review/RoleGate";
import { TranscriptDrawer } from "@/components/review/TranscriptDrawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

type Role = "dentist" | "patient" | "assistant_or_other" | "unknown";
type SpeakerStatus = "clear" | "review_needed" | "unresolved";
type ChecklistState = "found" | "review" | "missing";
type ToothSurface = "O" | "M" | "D" | "V" | "L";
type DentalChartCondition =
  | "caries"
  | "composite"
  | "amalgam"
  | "inlay"
  | "onlay"
  | "crown"
  | "bridge"
  | "prosthesis"
  | "implant"
  | "rct"
  | "missing"
  | "unclear";

type TranscriptUtterance = {
  speaker_id: string;
  text: string;
};

type TranscriptDiagnostics = {
  invalidLines: number[];
  speakerCount: number;
  utteranceCount: number;
};

type Speaker = {
  id: string;
  role: Role;
  status: SpeakerStatus;
  utterances: number;
  sample: string;
  reason?: string;
};

type NoteSentence = {
  sentence_id?: string;
  text: string;
  source_quote: string;
  source_role: Role;
};

type ClinicalNote = {
  patient_complaint: NoteSentence[];
  history: NoteSentence[];
  clinical_findings: NoteSentence[];
  assessment: NoteSentence[];
  treatment_plan: NoteSentence[];
  procedures_note: NoteSentence[];
  uncertain_items: string[];
  is_draft?: boolean;
};

type CandidateCode = {
  code: string;
  procedure_name: string;
  category: string;
};

type ChecklistItem = {
  item_id: string;
  label: string;
  status: ChecklistState;
  evidence_quote?: string | null;
};

type CodeMatchResult = {
  code: string;
  checklist: ChecklistItem[];
  match_state: string;
};

type ProcedureObject = {
  procedure_family: string;
  tooth_number_fdi?: number | null;
  surface_count?: string | null;
  surfaces?: ToothSurface[] | null;
  surface?: ToothSurface | ToothSurface[] | null;
  condition?: DentalChartCondition | string | null;
  canal_count?: string | null;
  status: string;
  source_quotes: string[];
};

type ProcedureReview = {
  procedure: ProcedureObject;
  review_state: string;
  candidates: CandidateCode[];
  match_results: CodeMatchResult[];
  ambiguity_note?: string | null;
  dentist_must_choose: boolean;
};

type PipelineReviewResponse = {
  session_id: string;
  status: string;
  review_state: string;
  stopped_at_stage?: string | null;
  next_action: string;
  role_review?: {
    speakers: {
      speaker_id: string;
      role: Role;
      status: SpeakerStatus;
      review_state: SpeakerStatus;
      utterance_count: number;
      reason?: string | null;
    }[];
    manual_review_required: boolean;
  } | null;
  dentist_review?: {
    note: ClinicalNote;
    procedures: ProcedureReview[];
    uncertain_items: string[];
  } | null;
  audio_processing?: {
    transcript?: {
      utterances: {
        speaker_id: string;
        text: string;
      }[];
    } | null;
  } | null;
  export_payload?: ExportPayload | null;
};

type ExportPayload = {
  session_id: string;
  clinical_note_text: string;
  selected_codes: string[];
  audit: {
    action: string;
    reviewer_user_id?: string | null;
    approved: boolean;
    created_at_utc: string;
    source: string;
  };
  warning: string;
};

type NoteSectionId = "patient_complaint" | "history" | "clinical_findings" | "assessment" | "treatment_plan" | "procedures_note";

type NoteSection = {
  id: NoteSectionId;
  title: string;
  lines: NoteSectionLine[];
};

type NoteSectionLine = {
  text: string;
  source_quote?: string;
  source_role?: Role;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const AUTH_HEADERS = {
  "X-Tandela-Clinic-Id": process.env.NEXT_PUBLIC_TANDELA_CLINIC_ID ?? "dev-clinic",
  "X-Tandela-User-Id": process.env.NEXT_PUBLIC_TANDELA_USER_ID ?? "frontend-doctor",
  "X-Tandela-User-Role": process.env.NEXT_PUBLIC_TANDELA_USER_ROLE ?? "dentist",
};

const transcriptLinePattern = /^([A-Za-zÇĞİÖŞÜçğıöşü0-9_-]+)\s*:\s*(.+)$/;

type SpeechRecognitionEventLike = {
  results?: ArrayLike<ArrayLike<{ transcript?: string }>>;
};

type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  start: () => void;
};

type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

export default function ReviewPage() {
  const [sessionId] = useState(() => createSessionId());
  const [patientName] = useState("Demo Danışan");
  const [encounterAt] = useState(() => toDatetimeLocalValue(new Date()));
  const [transcriptText, setTranscriptText] = useState("");
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [selectedCode, setSelectedCode] = useState("FIX-KANAL-2K");
  const [approved, setApproved] = useState(false);
  const [response, setResponse] = useState<PipelineReviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportPayload, setExportPayload] = useState<ExportPayload | null>(null);
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const [editableNote, setEditableNote] = useState<ClinicalNote | null>(null);
  const [manualChartProcedures, setManualChartProcedures] = useState<ProcedureObject[]>([]);
  const [editCommand, setEditCommand] = useState("");
  const [editMessage, setEditMessage] = useState<string | null>(null);
  const [audioStatus, setAudioStatus] = useState<string | null>(null);
  const transcriptTextRef = useRef("");

  const utterances = useMemo(() => parseTranscript(transcriptText), [transcriptText]);
  const transcriptDiagnostics = useMemo(() => inspectTranscript(transcriptText), [transcriptText]);
  const canAnalyzeTranscript = transcriptDiagnostics.utteranceCount > 0 && transcriptDiagnostics.invalidLines.length === 0;

  const dentistReview = response?.dentist_review ?? null;
  const displayedNote = editableNote ?? dentistReview?.note ?? null;
  const procedures = dentistReview?.procedures ?? [];
  const chartProcedures = useMemo(
    () => [...procedures.map((procedure) => procedure.procedure), ...manualChartProcedures],
    [manualChartProcedures, procedures],
  );
  const noteSections = displayedNote ? noteSectionsFromBackend(displayedNote) : [];
  const needsRoleReview = response?.next_action === "review_speaker_roles";
  const hasAnalysisDraft = response?.next_action === "review_note_and_codes" && Boolean(displayedNote);
  const analysisState = approved
    ? "Kayda hazır"
    : hasAnalysisDraft
      ? "Taslak hazır"
      : needsRoleReview
        ? "Rol kontrolü gerekli"
        : isLoading
          ? "Analiz ediliyor"
          : transcriptText.trim()
            ? "Analize hazır"
            : "Kayıt bekleniyor";

  function appendLiveTranscriptLine(line: string) {
    setTranscriptText((current) => {
      const trimmed = current.trim();
      const next = trimmed ? `${trimmed}\n${line}` : line;
      transcriptTextRef.current = next;
      return next;
    });
  }

  function updateTranscriptText(value: string) {
    transcriptTextRef.current = value;
    setTranscriptText(value);
  }

  async function processAudioFallback(audioBlob: Blob | null) {
    if (transcriptTextRef.current.trim()) {
      window.setTimeout(() => void analyzeTranscript(), 600);
      return;
    }
    if (!audioBlob) {
      setAudioStatus("Ses kaydı alındı fakat transkript oluşmadı. Metni elle girebilir veya tekrar kayıt alabilirsiniz.");
      return;
    }
    setIsLoading(true);
    setError(null);
    setAudioStatus("Canlı transkript gelmedi; ses kaydı batch ASR ile işleniyor.");
    try {
      const form = new FormData();
      form.append("audio", audioBlob, `${sessionId}.webm`);
      const result = await postMultipartReviewResponse(`/sessions/${encodeURIComponent(sessionId)}/audio`, form);
      const audioTranscript = result.audio_processing?.transcript?.utterances ?? [];
      if (audioTranscript.length) {
        updateTranscriptText(audioTranscript.map((utterance) => `${utterance.speaker_id}: ${utterance.text}`).join("\n"));
      }
      applyBackendResponse(result, audioTranscript.map((utterance) => ({ speaker_id: utterance.speaker_id, text: utterance.text })));
      setAudioStatus("Ses işlendi; taslak incelemeye hazır.");
    } catch (caught) {
      setError(errorMessage(caught));
      setAudioStatus("Ses batch ASR ile işlenemedi. Transkripti elle girip Analiz Et ile devam edebilirsiniz.");
    } finally {
      setIsLoading(false);
    }
  }

  async function runTranscriptAnalysis(sourceUtterances: TranscriptUtterance[]) {
    return postReviewResponse("/sessions", {
      session_id: sessionId,
      utterances: sourceUtterances,
    });
  }

  async function analyzeTranscript() {
    if (!canAnalyzeTranscript) {
      setError("Transkriptte analiz edilemeyen satır var. Her satır A: metin formatında olmalı.");
      return;
    }
    setIsLoading(true);
    setError(null);
    setApproved(false);
    setExportPayload(null);
    setEditableNote(null);
    setManualChartProcedures([]);
    setEditCommand("");
    setEditMessage(null);
    setExportMessage(null);
    try {
      const result = await runTranscriptAnalysis(utterances);
      applyBackendResponse(result, utterances);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsLoading(false);
    }
  }

  async function approveRolesAndResume() {
    if (!needsRoleReview) {
      setError("Devam etmek için önce rol onayı gerektiren bir analiz sonucu olmalı.");
      return;
    }
    if (!canAnalyzeTranscript) {
      setError("Rol onayı öncesi transkript satırlarını düzeltin.");
      return;
    }
    setIsLoading(true);
    setError(null);
    setApproved(false);
    setExportPayload(null);
    try {
      const activeSessionId = response?.session_id ?? sessionId;
      const result = await postReviewResponse(`/sessions/${encodeURIComponent(activeSessionId)}/resume-role-review`, {
        utterances,
        corrected_roles: speakers.map((speaker) => ({
          speaker_id: speaker.id,
          role: speaker.role,
          status: "clear",
          reason: "Frontend review: hekim rolü onayladı.",
        })),
      });
      setSpeakers((current) =>
        current.map((speaker) => ({
          ...speaker,
          status: "clear",
          reason: speaker.reason ?? "Frontend review: hekim rolü onayladı.",
        })),
      );
      applyBackendResponse(result);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsLoading(false);
    }
  }

  async function approveClinicalReview() {
    if (!hasAnalysisDraft || !displayedNote) {
      setError("Onay için önce klinik not ve kod taslağı oluşturulmalı.");
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const activeSessionId = response?.session_id ?? sessionId;
      const result = await postReviewResponse(`/sessions/${encodeURIComponent(activeSessionId)}/approve`, {
        selected_codes: selectedCode ? [selectedCode] : [],
        reviewer_user_id: "frontend-doctor",
        approved: true,
        approved_note: displayedNote,
      });
      setApproved(true);
      setExportPayload(result.export_payload ?? null);
      setExportMessage("Hekim onayı kaydedildi; çıktı kopyalama ve indirme için hazır.");
      setResponse((current) => ({
        ...(current ?? result),
        status: result.status,
        next_action: result.next_action,
        stopped_at_stage: result.stopped_at_stage,
        export_payload: result.export_payload,
      }));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsLoading(false);
    }
  }

  function applyBackendResponse(result: PipelineReviewResponse, sourceUtterances: TranscriptUtterance[] = utterances) {
    setResponse(result);
    setEditableNote(result.dentist_review?.note ?? null);
    setExportMessage(null);
    if (result.role_review) {
      setSpeakers(
        result.role_review.speakers.map((speaker) => ({
          id: speaker.speaker_id,
          role: speaker.role,
          status: speaker.status,
          utterances: speaker.utterance_count,
          sample: sampleForSpeaker(speaker.speaker_id, sourceUtterances),
          reason: speaker.reason ?? undefined,
        })),
      );
    }
    const firstCode = result.dentist_review?.procedures[0]?.candidates[0]?.code;
    if (firstCode) setSelectedCode(firstCode);
  }

  function updateSpeakerRole(id: string, role: Role) {
    setSpeakers((current) =>
      current.map((speaker) => (speaker.id === id ? { ...speaker, role, status: "clear" } : speaker)),
    );
  }

  function updateNoteSentence(sectionId: NoteSectionId, lineIndex: number, text: string) {
    setEditableNote((current) => {
      if (!current) return current;
      const section = current[sectionId];
      return {
        ...current,
        [sectionId]: section.map((sentence, index) => (index === lineIndex ? { ...sentence, text } : sentence)),
      };
    });
  }

  function applyEditCommand() {
    const command = editCommand.trim();
    if (!command || !displayedNote) return;
    const chartProcedure = parseDentalChartCommand(command);
    setEditableNote((current) => {
      if (!current) return current;
      return {
        ...current,
        procedures_note: [
          ...current.procedures_note,
          {
            text: command,
            source_quote: command,
            source_role: "dentist",
          },
        ],
      };
    });
    if (chartProcedure) {
      setManualChartProcedures((current) => [...current, chartProcedure]);
      setEditMessage("Düzeltme not taslağına eklendi ve diş şeması taslak olarak güncellendi.");
    } else {
      setEditMessage("Düzeltme not taslağına eklendi. Diş şeması için net FDI ve kondisyon bulunmadığından chart güncellenmedi.");
    }
    setEditCommand("");
  }

  function startEditDictation() {
    const SpeechRecognitionCtor = getSpeechRecognitionCtor();
    if (!SpeechRecognitionCtor) {
      setEditMessage("Tarayıcı sesli düzenlemeyi desteklemiyor. Düzeltmeyi yazarak girebilirsiniz.");
      return;
    }
    const recognition = new SpeechRecognitionCtor();
    recognition.lang = "tr-TR";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event: SpeechRecognitionEventLike) => {
      const transcript = event.results?.[0]?.[0]?.transcript?.trim();
      if (transcript) {
        setEditCommand((current) => (current.trim() ? `${current.trim()} ${transcript}` : transcript));
        setEditMessage("Sesli düzeltme alındı. Uygula ile not ve diş şeması taslağına işleyebilirsiniz.");
      }
    };
    recognition.onerror = () => {
      setEditMessage("Sesli düzeltme alınamadı. Düzeltmeyi yazarak girebilirsiniz.");
    };
    recognition.start();
  }

  async function copyExportToClipboard() {
    if (!exportPayload) return;
    const text = formatExportPayload(exportPayload);
    await navigator.clipboard.writeText(text);
    setExportMessage("Export metni panoya kopyalandı.");
  }

  function downloadExportTxt() {
    if (!exportPayload) return;
    const blob = new Blob([formatExportPayload(exportPayload)], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${exportPayload.session_id}-tandela-export.txt`;
    link.click();
    URL.revokeObjectURL(url);
    setExportMessage("TXT dosyası indirildi.");
  }

  if (approved && exportPayload) {
    return (
      <ApprovedExport
        message={exportMessage}
        onCopy={() => void copyExportToClipboard()}
        onDownloadTxt={downloadExportTxt}
      />
    );
  }

  if (needsRoleReview) {
    return (
      <RoleGate
        speakers={speakers}
        isLoading={isLoading}
        canApprove={canAnalyzeTranscript}
        onRoleChange={updateSpeakerRole}
        onApprove={() => void approveRolesAndResume()}
      />
    );
  }

  if (hasAnalysisDraft && displayedNote) {
    return (
      <main className="min-h-[calc(100vh-4rem)] bg-[#E7FEF8] p-4 text-[#0A1F1B] md:p-6">
        <div className="mx-auto max-w-[1600px] space-y-5">
          <section className="flex flex-wrap items-center justify-between gap-4 rounded-3xl border border-[#C0C9C1] bg-white p-5 shadow-sm">
            <div>
              <Badge className="rounded-full bg-[#E49545]/15 px-3 py-1 text-[#7A6221] hover:bg-[#E49545]/15">
                Taslak · Hekim onayı gereklidir
              </Badge>
              <h1 className="mt-3 text-2xl font-semibold tracking-tight">Analiz tamamlandı</h1>
              <p className="mt-1 text-sm text-[#404943]">Klinik not, diş şeması ve kod önerileri hekim incelemesine hazır.</p>
            </div>
            <Button
              type="button"
              className="h-11 rounded-full bg-[#31634B] px-6 font-semibold text-white hover:bg-[#4A7C63]"
              onClick={() => void approveClinicalReview()}
              disabled={isLoading || !displayedNote}
            >
              {isLoading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Save className="mr-2 size-4" />}
              Hekim Onayıyla Kayda Hazırla
            </Button>
          </section>

          <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
            <NoteDocument
              sections={noteSections}
              uncertainItems={dentistReview?.uncertain_items ?? []}
              onSentenceChange={updateNoteSentence}
            />
            <aside className="space-y-5">
              <ReviewEditPanel
                value={editCommand}
                message={editMessage}
                onChange={setEditCommand}
                onApply={applyEditCommand}
                onDictate={startEditDictation}
              />
              <DentalChartPanel procedures={chartProcedures} approved={approved} />
              <CodeSuggestionsPanel procedures={procedures} selectedCode={selectedCode} onSelectedCodeChange={setSelectedCode} />
              <TranscriptDrawer transcriptText={transcriptText} />
            </aside>
          </section>
        </div>
      </main>
    );
  }

  return (
    <main className="relative flex min-h-[calc(100vh-4rem)] flex-col items-center justify-center overflow-hidden bg-[#E7FEF8] px-6 py-10 text-[#0A1F1B]">
      <div className="pointer-events-none absolute inset-0 z-0 flex items-center justify-center">
        <div className="size-[600px] rounded-full bg-[#31634B]/5 blur-[120px]" />
      </div>

      <div className="relative z-10 flex w-full max-w-4xl flex-col items-center gap-10">
        <section className="w-full max-w-lg rounded-[32px] border border-[#C0C9C1] bg-white p-10 text-center shadow-sm md:p-12">
          <LiveTranscriptRecorder
            sessionId={sessionId}
            apiBase={API_BASE}
            disabled={isLoading}
            onTranscriptLine={appendLiveTranscriptLine}
            onRecordingStopped={(audioBlob) => void processAudioFallback(audioBlob)}
          />
          <Button
            type="button"
            className="mt-4 h-11 rounded-full bg-[#31634B] px-6 font-semibold text-white shadow-sm hover:bg-[#4A7C63]"
            onClick={() => void analyzeTranscript()}
            disabled={isLoading || !canAnalyzeTranscript}
          >
            {isLoading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Sparkles className="mr-2 size-4" />}
            Analiz Et
          </Button>
          <Button
            type="button"
            variant="ghost"
            className="mt-4 rounded-full text-[#31634B]"
            onClick={() => updateTranscriptText(sampleDashboardTranscript())}
          >
            Demo transkript yükle
          </Button>
        </section>

        <section className="flex h-80 w-full flex-col">
          <div className="mb-4 flex items-center justify-between px-4">
            <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-[#404943]">
              <span className="size-2 rounded-full bg-[#31634B] animate-pulse" />
              Canlı Transkript
            </span>
            <button className="text-xs font-semibold text-[#31634B] hover:underline" type="button" onClick={() => updateTranscriptText("")}>
              Kaydı Bitir
            </button>
          </div>
          <div className="flex-1 space-y-4 overflow-y-auto px-4 pb-20">
            {utterances.length ? (
              utterances.map((utterance, index) => (
                <TranscriptBubble key={`${utterance.speaker_id}-${index}`} speaker={utterance.speaker_id} text={utterance.text} />
              ))
            ) : (
              <EmptyListeningBubble />
            )}
          </div>
        </section>

        <section className="w-full rounded-3xl border border-[#C0C9C1] bg-white/70 p-4 shadow-sm backdrop-blur">
          <Textarea
            className="min-h-[120px] resize-y rounded-2xl border-[#C0C9C1] bg-white/80 text-sm leading-6"
            value={transcriptText}
            onChange={(event) => updateTranscriptText(event.target.value)}
            placeholder="A: Merhaba, şikayetiniz nedir?"
            aria-label="Transkript"
          />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-[#404943]">
            <span>{transcriptDiagnostics.speakerCount} konuşmacı · {transcriptDiagnostics.utteranceCount} ifade</span>
            <span>Taslak · Hekim onayı gereklidir</span>
          </div>
          {audioStatus ? <p className="mt-2 text-sm text-[#404943]">{audioStatus}</p> : null}
          {error ? <p className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive">{error}</p> : null}
        </section>
      </div>
    </main>
  );
}

async function postReviewResponse(path: string, body: unknown): Promise<PipelineReviewResponse> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { ...AUTH_HEADERS, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json() as Promise<PipelineReviewResponse>;
}

async function postMultipartReviewResponse(path: string, body: FormData): Promise<PipelineReviewResponse> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: AUTH_HEADERS,
    body,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json() as Promise<PipelineReviewResponse>;
}

function parseTranscript(text: string): TranscriptUtterance[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const match = transcriptLinePattern.exec(line);
      if (!match) return null;
      return { speaker_id: match[1], text: match[2] };
    })
    .filter((utterance): utterance is TranscriptUtterance => utterance !== null);
}

function inspectTranscript(text: string): TranscriptDiagnostics {
  const invalidLines: number[] = [];
  const speakers = new Set<string>();
  let utteranceCount = 0;
  text.split("\n").forEach((rawLine, index) => {
    const line = rawLine.trim();
    if (!line) return;
    const match = transcriptLinePattern.exec(line);
    if (!match) {
      invalidLines.push(index + 1);
      return;
    }
    speakers.add(match[1]);
    utteranceCount += 1;
  });
  return {
    invalidLines,
    speakerCount: speakers.size,
    utteranceCount,
  };
}

function createSessionId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `session-${crypto.randomUUID()}`;
  }
  return `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function formatExportPayload(payload: ExportPayload) {
  const codes = payload.selected_codes.length ? payload.selected_codes.join(", ") : "Kod seçilmedi";
  return [
    `Session: ${payload.session_id}`,
    `Onaylayan: ${payload.audit.reviewer_user_id ?? "Bilinmiyor"}`,
    `Onay zamanı: ${payload.audit.created_at_utc}`,
    `Seçilen kodlar: ${codes}`,
    "",
    payload.clinical_note_text || "Klinik not metni yok.",
  ].join("\n");
}

function noteSectionsFromBackend(note: ClinicalNote): NoteSection[] {
  return [
    { id: "patient_complaint", title: "Hasta şikayeti", lines: note.patient_complaint.map(noteLineFromSentence) },
    { id: "history", title: "Geçmiş", lines: note.history.map(noteLineFromSentence) },
    { id: "clinical_findings", title: "Klinik bulgular", lines: note.clinical_findings.map(noteLineFromSentence) },
    { id: "assessment", title: "Değerlendirme", lines: note.assessment.map(noteLineFromSentence) },
    { id: "treatment_plan", title: "Tedavi planı", lines: note.treatment_plan.map(noteLineFromSentence) },
    { id: "procedures_note", title: "İşlem notu", lines: note.procedures_note.map(noteLineFromSentence) },
  ];
}

function noteLineFromSentence(sentence: NoteSentence): NoteSectionLine {
  return {
    text: sentence.text,
    source_quote: sentence.source_quote,
    source_role: sentence.source_role,
  };
}

function sampleForSpeaker(speakerId: string, utterances: TranscriptUtterance[]) {
  return utterances.find((utterance) => utterance.speaker_id === speakerId)?.text ?? "Örnek ifade yok.";
}

function errorMessage(error: unknown) {
  if (error instanceof Error) return error.message;
  return "Backend bağlantısı başarısız.";
}

function StatusPill({ label }: { label: string }) {
  const isReady = label === "Taslak hazır" || label === "Kayda hazır";
  return (
    <span className="inline-flex h-11 items-center rounded-full border border-[#DDE3E0] bg-[#F8F9F7] px-3 text-sm font-medium shadow-sm">
      <CheckCircle2 className={`mr-2 size-4 ${isReady ? "text-[#4A7C63]" : "text-muted-foreground"}`} />
      {label}
    </span>
  );
}

function ReviewEditPanel({
  value,
  message,
  onChange,
  onApply,
  onDictate,
}: {
  value: string;
  message: string | null;
  onChange: (value: string) => void;
  onApply: () => void;
  onDictate: () => void;
}) {
  return (
    <Card className="overflow-hidden border-[#DDE3E0] bg-white shadow-sm">
      <CardHeader className="border-b border-[#DDE3E0] px-5 py-4">
        <CardTitle className="text-base font-semibold tracking-tight text-[#202422]">Notu Düzenle</CardTitle>
        <p className="mt-1 text-xs font-medium text-[#6F7470]">Yazarak veya konuşarak taslağa ekleyin</p>
      </CardHeader>
      <CardContent className="space-y-3 p-5">
        <Textarea
          className="min-h-[112px] resize-y rounded-2xl border-[#DDE3E0] bg-[#F8F9F7] text-sm leading-6"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Örn: 44 numarada okluzal çürük var. 46 için kanal tedavisi planlandı."
          aria-label="Klinik not düzeltmesi"
        />
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" className="rounded-full border-[#DDE3E0] bg-white" onClick={onDictate}>
            <Mic className="mr-2 size-4" />
            Sesle Gir
          </Button>
          <Button
            type="button"
            className="rounded-full bg-[#31634B] px-5 font-semibold text-white hover:bg-[#4A7C63]"
            onClick={onApply}
            disabled={!value.trim()}
          >
            Uygula
          </Button>
        </div>
        {message ? <p className="rounded-xl bg-[#E1F9F2] px-3 py-2 text-sm leading-6 text-[#224F3B]">{message}</p> : null}
        <p className="text-xs leading-5 text-[#6F7470]">
          Diş şeması yalnızca net FDI numarası ve kondisyon varsa güncellenir; belirsiz ifadeler chart'a işlenmez.
        </p>
      </CardContent>
    </Card>
  );
}

function TranscriptBubble({ speaker, text }: { speaker: string; text: string }) {
  const normalized = speaker.trim().toUpperCase();
  const isDentistLike = normalized === "A" || normalized.includes("HEK");
  const align = isDentistLike ? "items-start" : "items-end";
  const label = isDentistLike ? "HEKİM" : normalized === "B" ? "HASTA" : `KONUŞMACI ${speaker}`;
  const labelSpacing = isDentistLike ? "ml-4" : "mr-4";
  const bubbleClass = isDentistLike
    ? "rounded-tl-none bg-[#4A7C63] text-[#E3FFED]"
    : "rounded-tr-none bg-[#BCEED2] text-[#002114]";

  return (
    <div className={`flex flex-col ${align}`}>
      <span className={`mb-1 text-[10px] font-bold text-[#31634B] ${labelSpacing}`}>{label}</span>
      <div className={`max-w-md rounded-2xl p-4 shadow-sm ${bubbleClass}`}>
        <p className="text-sm leading-6">{text}</p>
      </div>
    </div>
  );
}

function getSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  const maybeWindow = window as typeof window & {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return maybeWindow.SpeechRecognition ?? maybeWindow.webkitSpeechRecognition ?? null;
}

function parseDentalChartCommand(command: string): ProcedureObject | null {
  const normalized = command.toLocaleLowerCase("tr-TR");
  if (/\b(değil|degil|yok|gündemde değil|gundemde degil|iptal)\b/.test(normalized)) return null;

  const tooth = extractToothNumber(normalized);
  const condition = extractCondition(normalized);
  if (!tooth || !condition) return null;

  return {
    procedure_family: procedureFamilyForCondition(condition),
    tooth_number_fdi: tooth,
    surfaces: extractSurfaces(normalized),
    condition,
    status: normalized.includes("yapıldı") || normalized.includes("tamamlandı") ? "completed" : "planned",
    source_quotes: [command],
  };
}

function extractToothNumber(text: string) {
  const digitMatch = /\b([1-4][1-8])\b/.exec(text);
  if (digitMatch) return Number(digitMatch[1]);
  const words: Array<[RegExp, number]> = [
    [/(sağ|sag)\s+alt\s+(altı|alti|6)/, 46],
    [/(sol)\s+alt\s+(altı|alti|6)/, 36],
    [/(sağ|sag)\s+üst\s+(altı|alti|6)/, 16],
    [/(sol)\s+üst\s+(altı|alti|6)/, 26],
    [/kırk\s+altı|kirk\s+alti/, 46],
    [/kırk\s+dört|kirk\s+dort/, 44],
    [/otuz\s+altı|otuz\s+alti/, 36],
    [/yirmi\s+altı|yirmi\s+alti/, 26],
    [/on\s+altı|on\s+alti/, 16],
  ];
  return words.find(([pattern]) => pattern.test(text))?.[1] ?? null;
}

function extractCondition(text: string): DentalChartCondition | null {
  if (/çürük|curuk|caries|d3|d2/.test(text)) return "caries";
  if (/kompozit|dolgu/.test(text)) return "composite";
  if (/amalgam/.test(text)) return "amalgam";
  if (/kron|kaplama/.test(text)) return "crown";
  if (/implant/.test(text)) return "implant";
  if (/kanal|endodonti|rct/.test(text)) return "rct";
  if (/eksik|çekim|cekim/.test(text)) return "missing";
  return null;
}

function extractSurfaces(text: string): ToothSurface[] {
  const surfaces = new Set<ToothSurface>();
  if (/okluzal|oklüzal|occlusal|\bo\b/.test(text)) surfaces.add("O");
  if (/meziyal|mesial|\bm\b/.test(text)) surfaces.add("M");
  if (/distal|\bd\b/.test(text)) surfaces.add("D");
  if (/vestibul|bukkal|bukal|\bv\b/.test(text)) surfaces.add("V");
  if (/lingual|palatinal|\bl\b/.test(text)) surfaces.add("L");
  if (/\bmod\b/.test(text)) {
    surfaces.add("M");
    surfaces.add("O");
    surfaces.add("D");
  }
  return Array.from(surfaces);
}

function procedureFamilyForCondition(condition: DentalChartCondition) {
  if (condition === "rct") return "kanal_tedavisi";
  if (condition === "composite") return "kompozit_dolgu";
  if (condition === "missing") return "dis_cekimi";
  if (condition === "caries") return "caries";
  return condition;
}

function EmptyListeningBubble() {
  return (
    <div className="flex flex-col items-end">
      <span className="mb-1 mr-4 text-[10px] font-bold text-[#3A6751]">HASTA</span>
      <div className="max-w-md rounded-2xl rounded-tr-none border border-dashed border-[#3A6751]/30 bg-[#BCEED2]/50 p-4 text-[#406D57] shadow-sm">
        <p className="flex items-center gap-2 text-sm italic leading-6">
          <span className="flex gap-1">
            <span className="size-1 rounded-full bg-[#3A6751] animate-bounce" />
            <span className="size-1 rounded-full bg-[#3A6751] animate-bounce [animation-delay:-0.15s]" />
            <span className="size-1 rounded-full bg-[#3A6751] animate-bounce [animation-delay:-0.3s]" />
          </span>
          Dinleniyor...
        </p>
      </div>
    </div>
  );
}

function EmptyClinicalNote() {
  return (
    <Card className="min-h-[760px] border-[#DDE3E0] bg-white shadow-sm">
      <CardHeader className="border-b border-[#DDE3E0] p-7 md:p-10">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#6F7470]">Klinik Not Taslağı</p>
            <CardTitle className="mt-3 text-3xl font-semibold tracking-tight">Kapsamlı Muayene</CardTitle>
          </div>
          <Badge className="rounded-full bg-[#E49545]/15 px-3 py-1.5 text-xs font-semibold text-[#7A6221] hover:bg-[#E49545]/15">
            Taslak · Hekim onayı gereklidir
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="flex min-h-[590px] items-center justify-center p-10">
        <div className="max-w-md text-center">
          <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-[#4A7C63]/10 text-[#2D5A45]">
            <ClipboardCheck className="size-7" aria-hidden="true" />
          </div>
          <h2 className="mt-5 text-xl font-semibold tracking-tight">Görüşme analiz edildiğinde not taslağı burada açılır</h2>
          <p className="mt-3 text-sm leading-6 text-[#6F7470]">
            Şikayet, anamnez, bulgu, değerlendirme ve tedavi planı tek doküman olarak hazırlanır.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function EmptyCodesCard() {
  return (
    <Card className="overflow-hidden border-[#DDE3E0] bg-white shadow-sm">
      <CardHeader className="border-b border-[#DDE3E0] px-5 py-4">
        <CardTitle className="text-base font-semibold tracking-tight">Kod Önerileri</CardTitle>
        <p className="mt-1 text-xs font-medium text-[#6F7470]">Kapalı kod veritabanı</p>
      </CardHeader>
      <CardContent className="p-5">
        <p className="rounded-2xl border border-dashed border-[#DDE3E0] bg-[#F8F9F7] px-4 py-4 text-sm leading-6 text-[#6F7470]">
          Analiz tamamlandığında aday kodlar ve checklist burada görünür. Kod uydurulmaz.
        </p>
      </CardContent>
    </Card>
  );
}

function SafetyCard() {
  return (
    <Card className="border-[#DDE3E0] bg-[#F8F9F7] shadow-sm">
      <CardContent className="p-5">
        <div className="flex items-start gap-3">
          <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-[#4A7C63]/12 text-[#2D5A45]">
            <ShieldCheck className="size-4" aria-hidden="true" />
          </div>
          <div>
            <p className="text-sm font-semibold text-[#202422]">Klinik güvenlik</p>
            <p className="mt-1 text-sm leading-6 text-[#6F7470]">
              Tüm çıktılar hekim onayına kadar taslaktır. Onay verilmeden export oluşturulmaz.
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function sampleDashboardTranscript() {
  return `A: Merhaba, şikayetiniz nedir?
B: Sağ alt tarafta iki gündür ağrım var, özellikle yemek yerken zonkluyor.
A: Ağzınızı açın lütfen. Sağ alt altıda, yani 46 numarada derin çürük görüyorum.
C: Hocam röntgeni açıyorum.
A: Perküsyonda hassasiyet var. Kanal tedavisi gerekebilir. Bugün geçici dolgu yapıp kanal tedavisi planlayalım.
B: Benim dişim iltihaplı mı yani?
A: Röntgene göre periapikal bölgede şüpheli bir görüntü var, kesin değerlendirme için endodontik muayeneyle ilerleyeceğiz.
A: 46 numara için kanal tedavisi planlandı, geçici restorasyon yapılacak.`;
}

function toDatetimeLocalValue(date: Date) {
  const offsetMs = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function formatEncounterDate(value: string) {
  if (!value) return "Tarih yok";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}
