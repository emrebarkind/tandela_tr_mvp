"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, ClipboardCheck, FileText, Loader2, Mic, PencilLine, Save, ShieldCheck, Timer, X } from "lucide-react";
import { useHeader } from "@/components/app/HeaderContext";
import { ApprovedExport } from "@/components/review/ApprovedExport";
import { DentalChartPanel } from "@/components/review/DentalChartPanel";
import { LiveTranscriptRecorder } from "@/components/review/LiveTranscriptRecorder";
import { TranscriptDrawer } from "@/components/review/TranscriptDrawer";
import { Badge } from "@/components/ui/badge";
import { DraftBadge } from "@/components/ui/draft-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { fetchPatients, type PatientSummary } from "@/lib/patients-api";
import type { PerioSessionResult } from "@/components/review/PerioChartPanel";

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
type ManualDentalCondition = Exclude<DentalChartCondition, "unclear">;

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

type RoleAssignmentSnapshot = {
  assignments: {
    speaker_id: string;
    role: Role;
    status: SpeakerStatus;
    utterance_count: number;
    reason?: string | null;
  }[];
};

type SessionReviewSnapshot = {
  clinical_pipeline?: {
    role_assignment?: RoleAssignmentSnapshot | null;
  } | null;
};

type NoteSentence = {
  sentence_id?: string;
  text: string;
  source_quote: string;
  source_role: Role;
  source_speaker?: string | null;
  source_role_confidence?: "clear" | "uncertain";
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
  is_manual?: boolean;
  manual_note?: string | null;
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
  role_review_required?: boolean;
  uncertain_speakers?: {
    speaker_id: string;
    tentative_role: Role;
    reason?: string | null;
  }[];
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
  source_speaker?: string | null;
  source_role_confidence?: "clear" | "uncertain";
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const AUTH_HEADERS = {
  "X-Tandela-Clinic-Id": process.env.NEXT_PUBLIC_TANDELA_CLINIC_ID ?? "dev-clinic",
  "X-Tandela-User-Id": process.env.NEXT_PUBLIC_TANDELA_USER_ID ?? "frontend-doctor",
  "X-Tandela-User-Role": process.env.NEXT_PUBLIC_TANDELA_USER_ROLE ?? "dentist",
};

const roleLabels: Record<Role, string> = {
  dentist: "Hekim",
  patient: "Hasta",
  assistant_or_other: "Asistan",
  unknown: "Bilinmeyen",
};

const transcriptLinePattern = /^([A-Za-zÇĞİÖŞÜçğıöşü0-9_-]+)\s*:\s*(.+)$/;

const analysisContainerVariants = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.14,
      delayChildren: 0.08,
    },
  },
};

const analysisItemVariants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.24 } },
};

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
type RecorderState = "idle" | "connecting" | "recording" | "paused" | "stopping";

export default function ReviewPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-muted-foreground">Görüşme ekranı hazırlanıyor...</div>}>
      <ReviewPageContent />
    </Suspense>
  );
}

function ReviewPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { clearHeader, setHeader } = useHeader();
  const [sessionId] = useState(() => createSessionId());
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
  const [isRolePanelOpen, setIsRolePanelOpen] = useState(false);
  const [roleDrafts, setRoleDrafts] = useState<Record<string, Role>>({});
  const [recorderCommand, setRecorderCommand] = useState<{ action: "start" | "stop" | "pause" | "resume"; nonce: number } | null>(null);
  const [recorderState, setRecorderState] = useState<RecorderState>("idle");
  const [recordingElapsedSec, setRecordingElapsedSec] = useState(0);
  const transcriptTextRef = useRef("");
  const [sessionMode, setSessionMode] = useState<"clinical_note" | "perio">("clinical_note");
  const [patients, setPatients] = useState<PatientSummary[]>([]);
  const [patientId, setPatientId] = useState(() => searchParams.get("patient_id") ?? "");
  const [perioDictation, setPerioDictation] = useState("");
  const patientName = patientId ? patientLabel(patients.find((patient) => patient.id === patientId)) : "Yeni Görüşme";

  const utterances = useMemo(() => parseTranscript(transcriptText), [transcriptText]);
  const transcriptDiagnostics = useMemo(() => inspectTranscript(transcriptText), [transcriptText]);
  const canAnalyzeTranscript = transcriptDiagnostics.utteranceCount > 0 && transcriptDiagnostics.invalidLines.length === 0;
  const speakerAssignmentsById = useMemo(
    () => new Map(speakers.map((speaker) => [speaker.id, speaker])),
    [speakers],
  );

  const dentistReview = response?.dentist_review ?? null;
  const displayedNote = editableNote ?? dentistReview?.note ?? null;
  const procedures = dentistReview?.procedures ?? [];
  const noteSections = displayedNote ? noteSectionsFromBackend(displayedNote) : [];
  const inferredChartProcedures = useMemo(
    () => inferChartProceduresFromNoteSections(noteSections, procedures.map((procedure) => procedure.procedure)),
    [noteSections, procedures],
  );
  const chartProcedures = useMemo(
    () => uniqueChartProcedures([...procedures.map((procedure) => procedure.procedure), ...inferredChartProcedures, ...manualChartProcedures]),
    [inferredChartProcedures, manualChartProcedures, procedures],
  );
  const needsRoleReview = Boolean(response?.role_review_required);
  const hasAnalysisDraft = Boolean(displayedNote) && (response?.next_action === "review_note_and_codes" || response?.role_review_required);
  const codeSuggestionCount = useMemo(() => procedures.reduce((total, procedure) => total + procedure.candidates.length, 0), [procedures]);
  const isRecorderActive = recorderState === "recording" || recorderState === "connecting" || recorderState === "paused";
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

  useEffect(() => {
    let active = true;
    void fetchPatients("")
      .then((items) => {
        if (active) setPatients(items);
      })
      .catch(() => {
        if (active) setPatients([]);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (approved) {
      clearHeader();
      return;
    }

    setHeader({
      title: patientName.trim() || "Yeni Görüşme",
      subtitle: formatEncounterDate(encounterAt),
      badge: <DraftBadge />,
      actions: hasAnalysisDraft && displayedNote ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            className="h-10 rounded-lg px-4 text-muted-foreground hover:bg-muted"
            onClick={() => {
              setResponse(null);
              setEditableNote(null);
              setManualChartProcedures([]);
              setApproved(false);
              setExportPayload(null);
            }}
          >
            <X className="mr-2 size-4" />
            Vazgeç
          </Button>
          <Button
            type="button"
            className="h-10 rounded-lg bg-primary px-5 font-semibold text-primary-foreground hover:bg-primary/80"
            onClick={() => void approveClinicalReview()}
            disabled={isLoading || !displayedNote}
          >
            {isLoading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Save className="mr-2 size-4" />}
            Onayla ve Kaydet
          </Button>
        </div>
      ) : undefined,
    });

    return () => clearHeader();
  }, [approved, clearHeader, displayedNote, encounterAt, hasAnalysisDraft, isLoading, patientName, setHeader]);

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
      if (patientId) form.append("patient_id", patientId);
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
      patient_id: patientId || null,
      utterances: sourceUtterances,
    });
  }

  async function analyzePerioDictation() {
    if (!patientId || !perioDictation.trim()) {
      setError("Perio diktesi için hasta ve dikte metni gereklidir.");
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      await postPerioResponse(`/sessions/${encodeURIComponent(sessionId)}/perio`, {
        patient_id: patientId,
        dictation: perioDictation.trim(),
      });
      router.push(`/session/${encodeURIComponent(sessionId)}`);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsLoading(false);
    }
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

  async function patchSpeakerRole(speakerId: string, role: Role) {
    if (!response?.session_id) return;
    setIsLoading(true);
    setError(null);
    setApproved(false);
    setExportPayload(null);
    try {
      const activeSessionId = response?.session_id ?? sessionId;
      const result = await patchReviewResponse(`/sessions/${encodeURIComponent(activeSessionId)}/speaker-role`, {
        speaker_id: speakerId,
        role,
        reason: "Frontend inline rol düzeltmesi.",
      });
      setSpeakers((current) =>
        current.map((speaker) => (speaker.id === speakerId ? { ...speaker, role, status: "clear" } : speaker)),
      );
      applyBackendResponse(result);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsLoading(false);
    }
  }

  async function applyRoleDrafts() {
    const entries = Object.entries(roleDrafts);
    if (!response?.session_id || !entries.length) return;
    const hasUnknownRole = speakers
      .filter((speaker) => speaker.status !== "clear" || speaker.role === "unknown")
      .some((speaker) => (roleDrafts[speaker.id] ?? speaker.role) === "unknown");
    if (hasUnknownRole) {
      setError("Rolleri uygulamadan önce tüm belirsiz konuşmacılar için Hekim/Hasta/Asistan seçin.");
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      let latest: PipelineReviewResponse | null = null;
      for (const [speakerId, role] of entries) {
        latest = await patchReviewResponse(`/sessions/${encodeURIComponent(response.session_id)}/speaker-role`, {
          speaker_id: speakerId,
          role,
          reason: "Frontend toplu rol düzeltmesi.",
        });
      }
      if (latest) applyBackendResponse(latest);
      setIsRolePanelOpen(false);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsLoading(false);
    }
  }

  async function addManualFinding(finding: { tooth_number_fdi: number; condition: ManualDentalCondition; note?: string }) {
    const activeSessionId = response?.session_id ?? sessionId;
    const optimisticProcedure: ProcedureObject = {
      procedure_family: manualConditionFamily(finding.condition),
      tooth_number_fdi: finding.tooth_number_fdi,
      condition: finding.condition,
      status: "performed",
      source_quotes: [finding.note?.trim() || "Hekim tarafından manuel eklendi"],
      is_manual: true,
      manual_note: finding.note?.trim() || null,
    };
    setManualChartProcedures((current) => [...current, optimisticProcedure]);
    try {
      const result = await postReviewResponse(`/sessions/${encodeURIComponent(activeSessionId)}/findings`, finding);
      setManualChartProcedures([]);
      applyBackendResponse(result);
    } catch (error) {
      setManualChartProcedures((current) => current.filter((item) => item !== optimisticProcedure));
      throw error;
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
    if (result.dentist_review?.note) {
      setEditableNote(result.dentist_review.note);
    }
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
      setRoleDrafts(
        Object.fromEntries(
          result.role_review.speakers
            .filter((speaker) => speaker.status !== "clear" || speaker.role === "unknown")
            .map((speaker) => [speaker.speaker_id, speaker.role]),
        ),
      );
    }
    const firstCode = result.dentist_review?.procedures[0]?.candidates[0]?.code;
    if (firstCode) setSelectedCode(firstCode);
    void hydrateSpeakerAssignments(result.session_id, sourceUtterances);
  }

  async function hydrateSpeakerAssignments(activeSessionId: string, sourceUtterances: TranscriptUtterance[]) {
    try {
      const snapshotResponse = await fetch(`${API_BASE}/sessions/${encodeURIComponent(activeSessionId)}/review`, {
        headers: AUTH_HEADERS,
        cache: "no-store",
      });
      if (!snapshotResponse.ok) return;
      const snapshot = (await snapshotResponse.json()) as SessionReviewSnapshot;
      const assignments = snapshot.clinical_pipeline?.role_assignment?.assignments;
      if (!assignments?.length) return;
      setSpeakers(
        assignments.map((assignment) => ({
          id: assignment.speaker_id,
          role: assignment.role,
          status: assignment.status,
          utterances: assignment.utterance_count,
          sample: sampleForSpeaker(assignment.speaker_id, sourceUtterances),
          reason: assignment.reason ?? undefined,
        })),
      );
    } catch {
      // Var olan role_review etiketlerini koru; başarısız hydrate için rol uydurma.
    }
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

  if (sessionMode === "perio") {
    return (
      <main className="min-h-[calc(100vh-4rem)] bg-background p-4 md:p-6">
        <div className="mx-auto w-full max-w-[1680px] space-y-5">
          <SessionModeSelector mode={sessionMode} onChange={setSessionMode} />
          <section className="grid min-h-[720px] overflow-hidden rounded-[32px] border border-border bg-card shadow-panel lg:grid-cols-[minmax(320px,0.44fr)_minmax(420px,0.56fr)]">
            <div className="border-b border-border p-6 lg:border-b-0 lg:border-r">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Yeni Perio Seansı</p>
              <h1 className="mt-2 font-heading text-2xl font-semibold tracking-tight">Periodontal Dikte</h1>
              <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
                Altı nokta ölçümlerini dikte edin; analiz kayıt tamamlandıktan sonra batch çalışır.
              </p>
              <div className="mt-8">
                <label className="mb-2 block text-sm font-semibold">Hasta</label>
                <Select value={patientId} onValueChange={(value) => setPatientId(value ?? "")}>
                  <SelectTrigger className="h-11 w-full border-border bg-background">
                    <SelectValue>{patientId ? patientLabel(patients.find((patient) => patient.id === patientId)) : "Hasta seçin"}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {patients.map((patient) => (
                      <SelectItem key={patient.id} value={patient.id}>{patientLabel(patient)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex min-h-0 flex-col bg-background/60 p-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Dikte</p>
                  <h2 className="mt-2 font-heading text-xl font-semibold">Perio ölçümlerini girin</h2>
                </div>
              </div>
              <Textarea
                id="perio-dictation"
                value={perioDictation}
                onChange={(event) => setPerioDictation(event.target.value)}
                placeholder="Örn. 16 bukkal üç dört dört, mobilite bir, furkasyon iki bukkal."
                className="mt-6 min-h-[360px] flex-1 resize-y rounded-2xl border-border bg-card text-sm leading-6"
              />
              {error ? <p className="mt-4 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}
              <div className="mt-5 flex justify-end">
                <Button className="h-11 px-5" onClick={() => void analyzePerioDictation()} disabled={isLoading || !patientId || !perioDictation.trim()}>
                  {isLoading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <ClipboardCheck className="mr-2 size-4" />}
                  Analiz Et
                </Button>
              </div>
            </div>
          </section>
        </div>
      </main>
    );
  }

  return (
    <main className="relative min-h-[calc(100vh-4rem)] overflow-hidden bg-background pb-24 text-foreground">
      <div className="mx-auto w-full max-w-[1680px] px-4 pt-4 md:px-6">
        <SessionModeSelector mode={sessionMode} onChange={setSessionMode} />
      </div>
      <div className="mx-auto grid min-h-[calc(100vh-10rem)] w-full max-w-[1680px] gap-5 px-4 py-4 md:px-6 min-[760px]:grid-cols-[minmax(300px,0.44fr)_minmax(320px,0.56fr)]">
        <section className="flex min-h-[720px] flex-col overflow-hidden rounded-[32px] border border-border bg-card shadow-panel">
          <div className="border-b border-border p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Yeni Görüşme</p>
                <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">Ses ve Transkript</h1>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  Transkript canlı akar; analiz kayıt bittikten sonra batch çalışır.
                </p>
              </div>
              <StatusPill label={analysisState} />
            </div>
          </div>

          <div className="border-b border-border p-6">
            <LiveTranscriptRecorder
              sessionId={sessionId}
              apiBase={API_BASE}
              disabled={isLoading}
              showInlineControls={false}
              controlCommand={recorderCommand}
              onStateChange={setRecorderState}
              onElapsedChange={setRecordingElapsedSec}
              onTranscriptLine={appendLiveTranscriptLine}
              onRecordingStopped={(audioBlob) => void processAudioFallback(audioBlob)}
            />
          </div>

          <div className="flex min-h-0 flex-1 flex-col">
            <div className="flex items-center justify-between border-b border-border px-6 py-4">
              <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                <span className={`size-2 rounded-full ${isLoading ? "bg-primary" : transcriptText.trim() ? "bg-primary" : "bg-muted-foreground"}`} />
                Canlı Transkript
              </span>
              <span className="text-xs font-semibold text-muted-foreground">
                {transcriptDiagnostics.speakerCount} konuşmacı · {transcriptDiagnostics.utteranceCount} ifade
              </span>
            </div>
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto bg-background/60 px-5 py-5">
              {utterances.length ? (
                utterances.map((utterance, index) => (
                  <TranscriptBubble
                    key={`${utterance.speaker_id}-${index}`}
                    speaker={utterance.speaker_id}
                    text={utterance.text}
                    assignment={speakerAssignmentsById.get(utterance.speaker_id)}
                  />
                ))
              ) : (
                <EmptyListeningBubble />
              )}
            </div>
            <div className="border-t border-border bg-card/80 p-4">
              <Textarea
                className="min-h-[104px] resize-y rounded-2xl border-border bg-background text-sm leading-6"
                value={transcriptText}
                onChange={(event) => updateTranscriptText(event.target.value)}
                placeholder="A: Merhaba, şikayetiniz nedir?"
                aria-label="Transkript"
              />
              {audioStatus ? <p className="mt-2 text-sm text-muted-foreground">{audioStatus}</p> : null}
              {error ? <p className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive">{error}</p> : null}
            </div>
          </div>
        </section>

        <section className="min-h-[720px] overflow-hidden rounded-[32px] border border-border bg-card shadow-panel">
          <div className="flex items-start justify-between gap-4 border-b border-border p-6">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Analiz</p>
              <h2 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">Klinik Taslak</h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Sonuçlar backend tamamlandıktan sonra bölüm bölüm gösterilir.
              </p>
            </div>
          </div>

          <div className="h-[calc(100%-97px)] overflow-y-auto p-5">
            {needsRoleReview ? (
              <div className="mb-4 rounded-2xl border border-secondary bg-secondary px-4 py-3 text-sm text-foreground">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="font-semibold">Konuşmacı rolleri kesin değil — kontrol edin</p>
                  <div className="flex items-center gap-2">
                    <Badge className="rounded-full bg-card text-foreground hover:bg-card">
                      {response?.uncertain_speakers?.length ?? speakers.filter((speaker) => speaker.status !== "clear").length} konuşmacı belirsiz
                    </Badge>
                    <Button type="button" variant="outline" className="h-8 border-border bg-card text-xs text-foreground" onClick={() => setIsRolePanelOpen((value) => !value)}>
                      Rolleri Düzenle
                    </Button>
                  </div>
                </div>
                {isRolePanelOpen ? (
                  <RoleReviewPanel
                    speakers={speakers.filter((speaker) => speaker.status !== "clear" || speaker.role === "unknown")}
                    roleDrafts={roleDrafts}
                    isLoading={isLoading}
                    onRoleChange={(speakerId, role) => setRoleDrafts((current) => ({ ...current, [speakerId]: role }))}
                    onApply={() => void applyRoleDrafts()}
                  />
                ) : null}
              </div>
            ) : null}

            {hasAnalysisDraft && displayedNote ? (
              <motion.div initial="hidden" animate="show" variants={analysisContainerVariants}>
                <SmartReviewWorkspace
                  chartProcedures={chartProcedures}
                  procedures={procedures}
                  noteSections={noteSections}
                  uncertainItems={dentistReview?.uncertain_items ?? []}
                  selectedCode={selectedCode}
                  onSelectedCodeChange={setSelectedCode}
                  approved={approved}
                  isLoading={false}
                  editCommand={editCommand}
                  editMessage={editMessage}
                  onEditCommandChange={setEditCommand}
                  onApplyEditCommand={applyEditCommand}
                  onDictateEditCommand={startEditDictation}
                  onAddFinding={addManualFinding}
                />
              </motion.div>
            ) : (
              <AnalysisSkeleton isLoading={isLoading} hasTranscript={Boolean(transcriptText.trim())} />
            )}
          </div>
        </section>
      </div>

      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-card/92 px-4 py-3 shadow-panel backdrop-blur-md">
        <div className="mx-auto flex max-w-[1680px] flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <span className="inline-flex h-10 items-center gap-2 rounded-full border border-border bg-background px-3 font-semibold text-foreground">
              <Timer className="size-4 text-primary" />
              {formatDuration(recordingElapsedSec)}
            </span>
            <span>{analysisState}</span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="outline"
              className="h-10 rounded-full border-border bg-card px-4 text-muted-foreground"
              onClick={() => setRecorderCommand({ action: recorderState === "paused" ? "resume" : "pause", nonce: Date.now() })}
              disabled={isLoading || !(recorderState === "recording" || recorderState === "paused")}
            >
              {recorderState === "paused" ? "Sürdür" : "Duraklat"}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="h-10 rounded-full border-border bg-card px-4 text-primary"
              onClick={() => setRecorderCommand({ action: isRecorderActive ? "stop" : "start", nonce: Date.now() })}
              disabled={isLoading || recorderState === "connecting" || recorderState === "stopping"}
            >
              {isRecorderActive ? "Durdur" : "Kaydı Başlat"}
            </Button>
            <Button type="button" variant="ghost" className="h-10 rounded-full text-primary" onClick={() => updateTranscriptText(sampleDashboardTranscript())}>
              Demo transkript yükle
            </Button>
            <Button
              type="button"
              className="h-10 rounded-full bg-primary px-5 font-semibold text-primary-foreground hover:bg-primary"
              onClick={() => void analyzeTranscript()}
              disabled={isLoading || !canAnalyzeTranscript}
            >
              {isLoading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <ClipboardCheck className="mr-2 size-4" />}
              Analiz Et
            </Button>
          </div>
        </div>
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

async function postPerioResponse(path: string, body: unknown): Promise<PerioSessionResult> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { ...AUTH_HEADERS, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
  return response.json() as Promise<PerioSessionResult>;
}

function SessionModeSelector({ mode, onChange }: {
  mode: "clinical_note" | "perio";
  onChange: (mode: "clinical_note" | "perio") => void;
}) {
  return (
    <div className="flex w-full flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-2 shadow-card" aria-label="Görüşme türü">
      <div className="min-w-44 px-2 py-1">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">Görüşme türü</p>
        <p className="mt-0.5 text-sm text-foreground">Başlatacağınız klinik akışı seçin.</p>
      </div>
      <div className="inline-flex rounded-lg bg-muted p-1" role="group" aria-label="Görüşme türü seçenekleri">
        <Button type="button" className="h-10 gap-2 px-4" variant={mode === "clinical_note" ? "default" : "ghost"} onClick={() => onChange("clinical_note")}>
          <FileText className="size-4" aria-hidden="true" />
          Hasta Görüşmesi
        </Button>
        <Button type="button" className="h-10 gap-2 px-4" variant={mode === "perio" ? "default" : "ghost"} onClick={() => onChange("perio")}>
          <ClipboardCheck className="size-4" aria-hidden="true" />
          Perio Dikte
        </Button>
      </div>
    </div>
  );
}

function patientLabel(patient: PatientSummary | undefined) {
  if (!patient) return "Hasta seçin";
  const name = patient.initials?.trim() || "İsimsiz hasta";
  return patient.external_id ? `${name} · ${patient.external_id}` : name;
}

async function patchReviewResponse(path: string, body: unknown): Promise<PipelineReviewResponse> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
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

function formatDuration(totalSec: number) {
  const hours = Math.floor(totalSec / 3600).toString().padStart(2, "0");
  const minutes = Math.floor((totalSec % 3600) / 60).toString().padStart(2, "0");
  const seconds = (totalSec % 60).toString().padStart(2, "0");
  return `${hours}:${minutes}:${seconds}`;
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
    source_speaker: sentence.source_speaker,
    source_role_confidence: sentence.source_role_confidence,
  };
}

function inferChartProceduresFromNoteSections(noteSections: NoteSection[], existingProcedures: ProcedureObject[]) {
  const existingKeys = new Set(existingProcedures.map(chartProcedureKey));
  const inferred: ProcedureObject[] = [];

  noteSections.forEach((section) => {
    section.lines.forEach((line) => {
      const source = line.source_quote || line.text;
      const chartProcedure = parseDentalChartCommand(source);
      if (!chartProcedure) return;

      const key = chartProcedureKey(chartProcedure);
      if (existingKeys.has(key)) return;

      existingKeys.add(key);
      inferred.push({
        ...chartProcedure,
        source_quotes: [source],
      });
    });
  });

  return inferred;
}

function chartProcedureKey(procedure: ProcedureObject) {
  const tooth = procedure.tooth_number_fdi ?? "unknown";
  const condition = procedure.condition ?? procedure.procedure_family ?? "unknown";
  return `${tooth}:${condition}`;
}

function uniqueChartProcedures(procedures: ProcedureObject[]) {
  const seen = new Set<string>();
  return procedures.filter((procedure) => {
    const key = chartProcedureKey(procedure);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
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
    <span className="inline-flex h-11 items-center rounded-full border border-border bg-background px-3 text-sm font-medium shadow-card">
      <CheckCircle2 className={`mr-2 size-4 ${isReady ? "text-primary" : "text-muted-foreground"}`} />
      {label}
    </span>
  );
}

function AnalysisSkeleton({ isLoading, hasTranscript }: { isLoading: boolean; hasTranscript: boolean }) {
  const title = isLoading ? "Analiz hazırlanıyor" : hasTranscript ? "Analiz için hazır" : "Kayıt bekleniyor";
  const subtitle = isLoading
    ? "Backend batch pipeline tamamlanana kadar gerçek içerik gösterilmeyecek."
    : hasTranscript
      ? "Analiz Et ile klinik not, diş şeması ve kod taslağı üretilecek."
      : "Sol panelde konuşma başladığında transkript burada analiz bekleyecek.";

  return (
    <div className="space-y-5">
      <Card className="border-border bg-background shadow-card">
        <CardHeader className="border-b border-border px-5 py-4">
          <CardTitle className="text-base font-semibold tracking-tight text-foreground">{title}</CardTitle>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">{subtitle}</p>
        </CardHeader>
        <CardContent className="space-y-4 p-5">
          <div className="rounded-2xl border border-border bg-card p-4">
            <Skeleton className="h-4 w-36 bg-muted" />
            <div className="mt-5 space-y-3">
              <Skeleton className="h-4 w-full bg-muted" />
              <Skeleton className="h-4 w-11/12 bg-muted" />
              <Skeleton className="h-4 w-2/3 bg-muted" />
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border border-border bg-card p-4">
              <Skeleton className="h-4 w-28 bg-muted" />
              <div className="mt-5 grid grid-cols-8 gap-2">
                {Array.from({ length: 24 }, (_, index) => (
                  <Skeleton key={index} className="h-7 rounded-[45%] bg-muted" />
                ))}
              </div>
            </div>
            <div className="space-y-3 rounded-2xl border border-border bg-card p-4">
              <Skeleton className="h-4 w-28 bg-muted" />
              <Skeleton className="h-12 w-full rounded-xl bg-muted" />
              <Skeleton className="h-12 w-full rounded-xl bg-muted" />
              <Skeleton className="h-12 w-4/5 rounded-xl bg-muted" />
            </div>
          </div>
        </CardContent>
      </Card>
      <p className="rounded-2xl border border-border bg-card px-4 py-3 text-sm leading-6 text-muted-foreground">
        V1.5 kuralı: canlı transkript görünür; klinik analiz konuşma/kayıt bittikten sonra batch çalışır.
      </p>
    </div>
  );
}

function SmartReviewWorkspace({
  chartProcedures,
  procedures,
  noteSections,
  uncertainItems,
  selectedCode,
  onSelectedCodeChange,
  approved,
  isLoading,
  editCommand,
  editMessage,
  onEditCommandChange,
  onApplyEditCommand,
  onDictateEditCommand,
  onAddFinding,
}: {
  chartProcedures: ProcedureObject[];
  procedures: ProcedureReview[];
  noteSections: NoteSection[];
  uncertainItems: string[];
  selectedCode: string;
  onSelectedCodeChange: (code: string) => void;
  approved: boolean;
  isLoading: boolean;
  editCommand: string;
  editMessage: string | null;
  onEditCommandChange: (value: string) => void;
  onApplyEditCommand: () => void;
  onDictateEditCommand: () => void;
  onAddFinding: (finding: { tooth_number_fdi: number; condition: ManualDentalCondition; note?: string }) => Promise<void>;
}) {
  const [verifiedNotes, setVerifiedNotes] = useState<Record<string, boolean>>({});
  const [verifiedCodes, setVerifiedCodes] = useState<Record<string, boolean>>({});
  const [highlightedSource, setHighlightedSource] = useState<{ label: string; quote: string } | null>(null);
  const noteCards = noteSections.flatMap((section) =>
    section.lines.map((line, index) => ({
      key: `${section.id}-${index}-${line.source_quote ?? line.text}`,
      section: section.title,
      text: line.text,
      sourceQuote: line.source_quote,
      sourceRole: line.source_role,
      needsRoleReview: line.source_role_confidence === "uncertain",
    })),
  );
  const codeCards = procedures.flatMap((procedure, procedureIndex) =>
    procedure.candidates.map((candidate) => ({
      key: `${procedureIndex}-${candidate.code}`,
      code: candidate.code,
      title: candidate.procedure_name,
      category: candidate.category,
      tooth: procedure.procedure.tooth_number_fdi,
      sourceQuote: procedure.procedure.source_quotes?.[0],
      matchState: procedure.match_results.find((result) => result.code === candidate.code)?.match_state ?? "needs_review",
    })),
  );

  return (
    <TooltipProvider delay={180}>
      <div className="relative grid gap-5 md:grid-cols-[minmax(0,1fr)_340px] 2xl:grid-cols-[minmax(0,1fr)_420px]">
        <motion.section variants={analysisItemVariants} className="min-w-0 rounded-[32px] border border-border bg-card/80 p-4 shadow-panel backdrop-blur">
          <DentalChartPanel procedures={chartProcedures} approved={approved} onAddFinding={onAddFinding} layout="canvas" isLoading={isLoading} />
          <LivingVoiceOrb active={isLoading} highlightedSource={highlightedSource} />
        </motion.section>

        <aside className="space-y-4">
        <motion.div variants={analysisItemVariants}>
        <Card className="border-border bg-card/70 shadow-panel backdrop-blur-md">
          <CardHeader className="border-b border-border/70 px-5 py-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle className="flex items-center gap-2 text-base font-semibold tracking-tight text-foreground">
                  <FileText className="size-4 text-primary" aria-hidden="true" />
                  AI Taslağı
                </CardTitle>
                <p className="mt-1 text-xs font-medium text-muted-foreground">Öneri olarak gelir; son söz hekimde.</p>
              </div>
              <Tooltip>
                <TooltipTrigger>
                  <Badge className="rounded-full bg-secondary px-2.5 py-1 text-[11px] font-semibold text-foreground hover:bg-secondary">
                    AI taslağı
                  </Badge>
                </TooltipTrigger>
                <TooltipContent side="left" className="max-w-64 bg-foreground text-primary-foreground">
                  AI tarafından taslak olarak oluşturuldu. Doğruluğunu hekim kontrol eder.
                </TooltipContent>
              </Tooltip>
            </div>
          </CardHeader>
          <CardContent className="max-h-[420px] space-y-3 overflow-y-auto p-5">
            {noteCards.length ? noteCards.map((card, index) => (
              <motion.div
                key={card.key}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.22, delay: Math.min(index * 0.035, 0.18) }}
                onMouseEnter={() => card.sourceQuote ? setHighlightedSource({ label: card.section, quote: card.sourceQuote }) : null}
                onMouseLeave={() => setHighlightedSource(null)}
                className={`group rounded-2xl border p-4 backdrop-blur-md transition-all ${
                  verifiedNotes[card.key]
                    ? "border-ring/45 bg-primary/8"
                    : "border-border bg-card/55 hover:border-ring/45 hover:bg-card/80"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">{card.section}</p>
                    <p className="mt-2 text-sm leading-6 text-foreground">{card.text}</p>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className={`h-8 shrink-0 rounded-lg border-border bg-card/80 hover:bg-secondary ${
                      verifiedNotes[card.key] ? "text-primary" : "text-muted-foreground"
                    }`}
                    onClick={() => setVerifiedNotes((current) => ({ ...current, [card.key]: !current[card.key] }))}
                  >
                    <CheckCircle2 className="mr-1.5 size-3.5" />
                    {verifiedNotes[card.key] ? "Doğrulandı" : "Doğrula"}
                  </Button>
                </div>
                <button
                  type="button"
                  className="mt-3 inline-flex items-center rounded-lg text-xs font-semibold text-primary transition hover:text-foreground"
                  onClick={() => onEditCommandChange(card.text)}
                >
                  <PencilLine className="mr-1.5 size-3.5" aria-hidden="true" />
                  Düzenle
                </button>
                {card.sourceQuote ? (
                  <p className="mt-3 border-l-2 border-ring bg-card/60 py-1 pl-3 text-xs italic leading-5 text-muted-foreground transition-colors group-hover:bg-secondary group-hover:text-foreground">
                    Kaynak: {roleLabels[card.sourceRole ?? "unknown"]}: {card.sourceQuote}
                  </p>
                ) : null}
                {card.needsRoleReview ? (
                  <p className="mt-2 rounded-lg bg-secondary px-3 py-2 text-xs font-medium text-foreground">
                    Konuşmacı rolü kontrol edilmeli.
                  </p>
                ) : null}
              </motion.div>
            )) : (
              <p className="rounded-xl border border-dashed border-border bg-background px-4 py-3 text-sm text-muted-foreground">
                Not taslağı henüz oluşmadı.
              </p>
            )}
          </CardContent>
        </Card>
        </motion.div>

        <motion.div variants={analysisItemVariants}>
        <Card className="border-border bg-card/70 shadow-panel backdrop-blur-md">
          <CardHeader className="border-b border-border/70 px-5 py-4">
            <CardTitle className="text-base font-semibold tracking-tight text-foreground">Önerilen TDB Kodları</CardTitle>
            <p className="mt-1 text-xs font-medium text-muted-foreground">Kapalı kod veritabanından adaylar; son seçim hekimde.</p>
          </CardHeader>
          <CardContent className="space-y-3 p-5">
            {codeCards.length ? codeCards.map((card, index) => (
              <motion.button
                key={card.key}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.22, delay: Math.min(index * 0.035, 0.18) }}
                onMouseEnter={() => card.sourceQuote ? setHighlightedSource({ label: card.code, quote: card.sourceQuote }) : null}
                onMouseLeave={() => setHighlightedSource(null)}
                className={`group w-full rounded-2xl border p-4 text-left backdrop-blur-md transition ${
                  verifiedCodes[card.key]
                    ? "border-ring bg-primary/10"
                    : selectedCode === card.code
                    ? "border-ring bg-primary/10"
                    : "border-border bg-card/55 hover:border-ring/45 hover:bg-card/80"
                }`}
                type="button"
                onClick={() => onSelectedCodeChange(card.code)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-foreground">{card.code}</p>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">{card.title}</p>
                  </div>
                  <Badge className={`shrink-0 rounded-lg px-2.5 py-1 text-[11px] font-semibold ${codeStateClassName(card.matchState)}`}>
                    {codeStateLabel(card.matchState)}
                  </Badge>
                </div>
                <p className="mt-3 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                  {card.category} · FDI {card.tooth ?? "Belirsiz"}
                </p>
                {card.sourceQuote ? (
                  <p className="mt-3 border-l-2 border-ring bg-card/60 py-1 pl-3 text-xs italic leading-5 text-muted-foreground transition-colors group-hover:bg-secondary group-hover:text-foreground">
                    Kaynak: {card.sourceQuote}
                  </p>
                ) : null}
                <span
                  className="mt-3 inline-flex h-8 items-center rounded-lg border border-border bg-card px-3 text-xs font-semibold text-primary"
                  onClick={(event) => {
                    event.stopPropagation();
                    setVerifiedCodes((current) => ({ ...current, [card.key]: !current[card.key] }));
                  }}
                >
                  <CheckCircle2 className="mr-1.5 size-3.5" />
                  {verifiedCodes[card.key] ? "Doğrulandı" : "Doğrula"}
                </span>
              </motion.button>
            )) : (
              <p className="rounded-xl border border-dashed border-border bg-background px-4 py-3 text-sm text-muted-foreground">
                Kod önerisi için yeterli işlem bilgisi yok.
              </p>
            )}
          </CardContent>
        </Card>
        </motion.div>

        {uncertainItems.length ? (
          <motion.div variants={analysisItemVariants}>
          <Card className="border-secondary bg-secondary shadow-card">
            <CardHeader className="border-b border-secondary px-5 py-4">
              <CardTitle className="text-base font-semibold tracking-tight text-foreground">Unutulmuş olabilir</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 p-5">
              {uncertainItems.map((item, index) => (
                <p key={`${index}-${item}`} className="rounded-xl bg-card px-3 py-2 text-sm leading-6 text-foreground">
                  {item}
                </p>
              ))}
            </CardContent>
          </Card>
          </motion.div>
        ) : null}

        <motion.div variants={analysisItemVariants}>
        <ReviewEditPanel
          value={editCommand}
          message={editMessage}
          onChange={onEditCommandChange}
          onApply={onApplyEditCommand}
          onDictate={onDictateEditCommand}
        />
        </motion.div>
        </aside>
      </div>
    </TooltipProvider>
  );
}

function LivingVoiceOrb({ active, highlightedSource }: { active: boolean; highlightedSource: { label: string; quote: string } | null }) {
  return (
    <div className="pointer-events-none absolute bottom-5 left-5 z-10 flex max-w-[520px] items-end gap-3">
      <div className="relative grid size-16 shrink-0 place-items-center rounded-full border border-ring/30 bg-card/75 shadow-card backdrop-blur-md">
        <motion.span
          className="absolute inset-2 rounded-full border border-ring/25"
          animate={{ scale: active ? [1, 1.08, 1] : [1, 1.03, 1], opacity: active ? [0.4, 0.72, 0.4] : [0.28, 0.42, 0.28] }}
          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.span
          className="relative size-8 rounded-full bg-secondary"
          animate={{ y: active ? [0, -2, 0] : [0, 1, 0] }}
          transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
        />
      </div>
      <AnimatePresence>
        {highlightedSource ? (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.18 }}
            className="mb-1 rounded-2xl border border-ring/25 bg-card/85 px-4 py-3 shadow-card backdrop-blur-md"
          >
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Kaynak vurgusu · {highlightedSource.label}</p>
            <p className="mt-1 line-clamp-2 text-xs italic leading-5 text-muted-foreground">{highlightedSource.quote}</p>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}

function codeStateLabel(state: string) {
  if (state === "confirmed_by_documentation") return "Dokümantasyon Tam";
  if (state === "ambiguous_multiple_candidates") return "Hekim Seçmeli";
  if (state === "no_match") return "Eşleşme Yok";
  return "Eksik Bilgi";
}

function codeStateClassName(state: string) {
  if (state === "confirmed_by_documentation") return "bg-primary/15 text-primary";
  if (state === "ambiguous_multiple_candidates") return "bg-secondary text-foreground";
  if (state === "no_match") return "bg-muted text-muted-foreground";
  return "bg-secondary text-foreground";
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
    <Card className="overflow-hidden border-border bg-card shadow-card">
      <CardHeader className="border-b border-border px-5 py-4">
        <CardTitle className="text-base font-semibold tracking-tight text-foreground">Notu Düzenle</CardTitle>
        <p className="mt-1 text-xs font-medium text-muted-foreground">Yazarak veya konuşarak taslağa ekleyin</p>
      </CardHeader>
      <CardContent className="space-y-3 p-5">
        <Textarea
          className="min-h-[112px] resize-y rounded-2xl border-border bg-background text-sm leading-6"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Örn: 44 numarada okluzal çürük var. 46 için kanal tedavisi planlandı."
          aria-label="Klinik not düzeltmesi"
        />
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" className="rounded-full border-border bg-card" onClick={onDictate}>
            <Mic className="mr-2 size-4" />
            Sesle Gir
          </Button>
          <Button
            type="button"
            className="rounded-full bg-primary px-5 font-semibold text-primary-foreground hover:bg-primary"
            onClick={onApply}
            disabled={!value.trim()}
          >
            Uygula
          </Button>
        </div>
        {message ? <p className="rounded-xl bg-secondary px-3 py-2 text-sm leading-6 text-foreground">{message}</p> : null}
        <p className="text-xs leading-5 text-muted-foreground">
          Diş şeması yalnızca net FDI numarası ve kondisyon varsa güncellenir; belirsiz ifadeler chart'a işlenmez.
        </p>
      </CardContent>
    </Card>
  );
}

function RoleReviewPanel({
  speakers,
  roleDrafts,
  isLoading,
  onRoleChange,
  onApply,
}: {
  speakers: Speaker[];
  roleDrafts: Record<string, Role>;
  isLoading: boolean;
  onRoleChange: (speakerId: string, role: Role) => void;
  onApply: () => void;
}) {
  const hasUnknownRole = speakers.some((speaker) => (roleDrafts[speaker.id] ?? speaker.role) === "unknown");
  return (
    <div className="mt-4 space-y-3 rounded-xl border border-secondary bg-card p-3">
      {speakers.length ? (
        speakers.map((speaker) => (
          <div key={speaker.id} className="grid gap-3 rounded-lg border border-border bg-background p-3 md:grid-cols-[110px_180px_minmax(0,1fr)] md:items-center">
            <div>
              <p className="text-sm font-semibold text-foreground">Speaker {speaker.id}</p>
              <p className="mt-1 text-xs text-muted-foreground">{speaker.utterances} ifade</p>
            </div>
            <Select value={roleDrafts[speaker.id] ?? speaker.role} onValueChange={(value) => onRoleChange(speaker.id, value as Role)}>
              <SelectTrigger className="h-10 border-border bg-card text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="dentist">Hekim</SelectItem>
                <SelectItem value="patient">Hasta</SelectItem>
                <SelectItem value="assistant_or_other">Asistan</SelectItem>
                <SelectItem value="unknown">Bilinmiyor</SelectItem>
              </SelectContent>
            </Select>
            <div>
              <p className="text-sm leading-6 text-foreground">{speaker.sample}</p>
              {speaker.reason ? <p className="mt-1 text-xs italic leading-5 text-muted-foreground">{speaker.reason}</p> : null}
            </div>
          </div>
        ))
      ) : (
        <p className="text-sm text-muted-foreground">Belirsiz konuşmacı kalmadı.</p>
      )}
      <Button type="button" className="h-10 w-full bg-primary text-primary-foreground hover:bg-primary/80" onClick={onApply} disabled={isLoading || !speakers.length || hasUnknownRole}>
        Rolleri Uygula
      </Button>
    </div>
  );
}

function TranscriptReviewPanel({ transcriptText }: { transcriptText: string }) {
  return (
    <Card className="border-border bg-card shadow-card">
      <CardHeader className="border-b border-border px-6 py-5">
        <CardTitle className="text-lg font-semibold tracking-tight text-foreground">Transkript</CardTitle>
        <p className="mt-1 text-sm text-muted-foreground">Kaynak konuşma metni; klinik not ve bulgular bu metinden türetilir.</p>
      </CardHeader>
      <CardContent className="p-6">
        <pre className="max-h-[720px] overflow-auto whitespace-pre-wrap rounded-2xl border border-border bg-background p-5 text-sm leading-7 text-foreground">
          {transcriptText || "Transkript yok."}
        </pre>
      </CardContent>
    </Card>
  );
}

function TranscriptBubble({ speaker, text, assignment }: { speaker: string; text: string; assignment?: Speaker }) {
  const role = assignment?.role;
  const isUncertain = Boolean(assignment && (assignment.status !== "clear" || role === "unknown"));
  const align = role === "patient" ? "items-end" : "items-start";
  const labelSpacing = role === "patient" ? "mr-4" : "ml-4";
  const baseLabel = role === "dentist"
    ? "HEKİM"
    : role === "patient"
      ? "HASTA"
      : role === "assistant_or_other"
        ? "ASİSTAN/DİĞER"
        : `KONUŞMACI ${speaker}`;
  const label = isUncertain && role !== "unknown" ? `${baseLabel}?` : baseLabel;
  const bubbleClass = role === "dentist"
    ? "rounded-tl-none bg-primary text-primary-foreground"
    : role === "patient"
      ? "rounded-tr-none bg-secondary text-foreground"
      : "rounded-tl-none border border-border bg-card text-foreground";

  return (
    <div className={`flex flex-col ${align}`}>
      <span className={`mb-1 flex items-center gap-1 text-[10px] font-bold ${isUncertain ? "text-amber-700" : "text-primary"} ${labelSpacing}`}>
        {isUncertain ? <AlertTriangle className="size-3" aria-hidden="true" /> : null}
        {label}
      </span>
      <div className={`max-w-md rounded-2xl p-4 shadow-card ${bubbleClass}`}>
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

function manualConditionFamily(condition: ManualDentalCondition) {
  if (condition === "rct") return "kanal_tedavisi";
  if (condition === "composite") return "kompozit_dolgu";
  if (condition === "missing") return "dis_cekimi";
  return "manuel_bulgu";
}

function EmptyListeningBubble() {
  return (
    <div className="flex flex-col items-end">
      <span className="mb-1 mr-4 text-[10px] font-bold text-primary">HASTA</span>
      <div className="max-w-md rounded-2xl rounded-tr-none border border-dashed border-primary bg-secondary/50 p-4 text-muted-foreground shadow-card">
        <p className="flex items-center gap-2 text-sm italic leading-6">
          <span className="flex gap-1">
            <span className="size-1 rounded-full bg-primary animate-bounce" />
            <span className="size-1 rounded-full bg-primary animate-bounce [animation-delay:-0.15s]" />
            <span className="size-1 rounded-full bg-primary animate-bounce [animation-delay:-0.3s]" />
          </span>
          Dinleniyor...
        </p>
      </div>
    </div>
  );
}

function EmptyClinicalNote() {
  return (
    <Card className="min-h-[760px] border-border bg-card shadow-card">
      <CardHeader className="border-b border-border p-7 md:p-10">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Klinik Not Taslağı</p>
            <CardTitle className="mt-3 text-3xl font-semibold tracking-tight">Kapsamlı Muayene</CardTitle>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex min-h-[590px] items-center justify-center p-10">
        <div className="max-w-md text-center">
          <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-primary/10 text-primary">
            <ClipboardCheck className="size-7" aria-hidden="true" />
          </div>
          <h2 className="mt-5 text-xl font-semibold tracking-tight">Görüşme analiz edildiğinde not taslağı burada açılır</h2>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            Şikayet, anamnez, bulgu, değerlendirme ve tedavi planı tek doküman olarak hazırlanır.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function EmptyCodesCard() {
  return (
    <Card className="overflow-hidden border-border bg-card shadow-card">
      <CardHeader className="border-b border-border px-5 py-4">
        <CardTitle className="text-base font-semibold tracking-tight">Kod Önerileri</CardTitle>
        <p className="mt-1 text-xs font-medium text-muted-foreground">Kapalı kod veritabanı</p>
      </CardHeader>
      <CardContent className="p-5">
        <p className="rounded-2xl border border-dashed border-border bg-background px-4 py-4 text-sm leading-6 text-muted-foreground">
          Analiz tamamlandığında aday kodlar ve checklist burada görünür. Kod uydurulmaz.
        </p>
      </CardContent>
    </Card>
  );
}

function SafetyCard() {
  return (
    <Card className="border-border bg-background shadow-card">
      <CardContent className="p-5">
        <div className="flex items-start gap-3">
          <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-primary/12 text-primary">
            <ShieldCheck className="size-4" aria-hidden="true" />
          </div>
          <div>
            <p className="text-sm font-semibold text-foreground">Klinik güvenlik</p>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
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
