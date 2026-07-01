"use client";

import {
  AlertTriangle,
  BadgeCheck,
  CalendarClock,
  Check,
  ChevronDown,
  CircleDot,
  ClipboardList,
  Copy,
  Download,
  FileText,
  History,
  ListChecks,
  Loader2,
  Mic2,
  Play,
  Printer,
  RotateCcw,
  Save,
  ShieldCheck,
  Square,
  Upload,
  UserCheck,
} from "lucide-react";
import { Odontogram, type ToothConditionGroup } from "react-odontogram";
import "react-odontogram/style.css";
import { useEffect, useMemo, useRef, useState } from "react";

type Role = "dentist" | "patient" | "assistant_or_other" | "unknown";
type SpeakerStatus = "clear" | "review_needed" | "unresolved";
type ChecklistState = "found" | "review" | "missing";
type ProductMode = "clinical_notes" | "perio_dictation";
type PerioSite = "MB" | "B" | "DB" | "ML" | "L" | "DL";
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

type PerioSiteDraft = {
  pocket?: number;
  bleeding?: boolean;
  plaque?: boolean;
  furcation?: string;
  source?: string;
  review?: boolean;
};

type PerioToothDraft = {
  tooth: number;
  sites: Record<PerioSite, PerioSiteDraft>;
  source_quotes: string[];
  review: boolean;
};

type PerioDraft = {
  teeth: PerioToothDraft[];
  review_items: string[];
  source_utterances: number;
};

type SpeakerLabelledTranscript = {
  utterances: TranscriptUtterance[];
};

type AudioProcessResponse = {
  status: string;
  raw_audio_deleted: boolean;
  provider_status: string;
  message: string;
  warnings?: string[];
  transcript?: SpeakerLabelledTranscript | null;
};

type AudioJobResponse = {
  job_id: string;
  session_id: string;
  status: "queued" | "processing" | "done" | "error";
  result?: AudioProcessResponse | null;
  error?: string | null;
  created_at_utc: string;
  updated_at_utc: string;
};

type ConversationRecord = {
  id: string;
  patientName: string;
  encounterAt: string;
  durationSec: number;
  transcriptText: string;
  utteranceCount: number;
  speakerCount: number;
  status: string;
  nextAction: string;
  noteSectionCount: number;
  procedureCount: number;
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

type DentalSurfaceCondition = {
  tooth: number;
  surfaces: ToothSurface[];
  condition: DentalChartCondition | string;
  color: string;
  status: string;
};

type DentalChartAdapterResult = {
  teethConditions: ToothConditionGroup[];
  surfaceConditions: DentalSurfaceCondition[];
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
  export_payload?: ExportPayload | null;
  audio_processing?: AudioProcessResponse | null;
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

type RecordingState = "idle" | "recording" | "ready";
type LiveAsrState = "idle" | "listening";

type BrowserSpeechRecognitionAlternative = {
  transcript: string;
};

type BrowserSpeechRecognitionResult = {
  isFinal: boolean;
  0: BrowserSpeechRecognitionAlternative;
};

type BrowserSpeechRecognitionEvent = {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: BrowserSpeechRecognitionResult;
  };
};

type BrowserSpeechRecognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: BrowserSpeechRecognitionEvent) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type BrowserSpeechRecognitionConstructor = new () => BrowserSpeechRecognition;

declare global {
  interface Window {
    SpeechRecognition?: BrowserSpeechRecognitionConstructor;
    webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor;
  }
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const AUTH_HEADERS = {
  "X-Tandela-Clinic-Id": process.env.NEXT_PUBLIC_TANDELA_CLINIC_ID ?? "dev-clinic",
  "X-Tandela-User-Id": process.env.NEXT_PUBLIC_TANDELA_USER_ID ?? "frontend-doctor",
  "X-Tandela-User-Role": process.env.NEXT_PUBLIC_TANDELA_USER_ROLE ?? "dentist",
};

const sampleTranscript = `A: Merhaba, şikayetiniz nedir?
B: Sağ alt tarafta iki gündür ağrım var, özellikle yemek yerken zonkluyor.
A: Ağzınızı açın lütfen. Sağ alt altıda, yani 46 numarada derin çürük görüyorum.
C: Hocam röntgeni açıyorum.
A: Perküsyonda hassasiyet var. Kanal tedavisi gerekebilir. Bugün geçici dolgu yapıp kanal tedavisi planlayalım.
B: Benim dişim iltihaplı mı yani?
A: Röntgene göre periapikal bölgede şüpheli bir görüntü var, kesin değerlendirme için endodontik muayeneyle ilerleyeceğiz.
A: 46 numara için kanal tedavisi planlandı, geçici restorasyon yapılacak.`;

const fallbackSpeakers: Speaker[] = [
  {
    id: "A",
    role: "dentist",
    status: "clear",
    utterances: 5,
    sample: "46 numarada derin çürük görüyorum.",
  },
  {
    id: "B",
    role: "patient",
    status: "clear",
    utterances: 2,
    sample: "Sağ alt tarafta iki gündür ağrım var.",
  },
  {
    id: "C",
    role: "assistant_or_other",
    status: "review_needed",
    utterances: 1,
    sample: "Hocam röntgeni açıyorum.",
  },
];

const fallbackNoteSections: NoteSection[] = [
  {
    id: "patient_complaint",
    title: "Hasta şikayeti",
    lines: [
      {
        text: "Sağ alt tarafta iki gündür ağrı var, özellikle yemek yerken zonkluyor.",
        source_quote: "Sağ alt tarafta iki gündür ağrım var.",
        source_role: "patient",
      },
      {
        text: "Hasta dişinde iltihap olabileceğine dair endişe belirtti.",
        source_quote: "Benim dişim iltihaplı mı yani?",
        source_role: "patient",
      },
    ],
  },
  {
    id: "clinical_findings",
    title: "Klinik bulgular",
    lines: [
      { text: "46 numarada derin çürük görüyorum.", source_quote: "46 numarada derin çürük görüyorum.", source_role: "dentist" },
      { text: "Perküsyonda hassasiyet var.", source_quote: "Perküsyonda hassasiyet var.", source_role: "dentist" },
      {
        text: "Periapikal bölgede şüpheli bir görüntü var.",
        source_quote: "periapikal bölgede şüpheli bir görüntü var",
        source_role: "dentist",
      },
    ],
  },
  {
    id: "treatment_plan",
    title: "Tedavi planı",
    lines: [
      {
        text: "46 numara için kanal tedavisi planlandı.",
        source_quote: "46 numara için kanal tedavisi planlandı",
        source_role: "dentist",
      },
    ],
  },
  {
    id: "procedures_note",
    title: "İşlem notu",
    lines: [
      { text: "Kanal tedavisi planlandı.", source_quote: "kanal tedavisi planlandı", source_role: "dentist" },
      {
        text: "Geçici restorasyon durumu çelişik; hekim onayı gerekiyor.",
        source_quote: "Bugün geçici dolgu yapıp... geçici restorasyon yapılacak",
        source_role: "dentist",
      },
    ],
  },
];

const fallbackChecklist: ChecklistItem[] = [
  { item_id: "tooth_number", label: "Diş numarası", status: "found", evidence_quote: "46" },
  {
    item_id: "canal_count",
    label: "Kanal sayısı",
    status: "review",
    evidence_quote: "Kanal sayısı söylenmedi",
  },
  {
    item_id: "endo_diagnosis",
    label: "Endodontik gerekçe",
    status: "found",
    evidence_quote: "Derin çürük ve perküsyon hassasiyeti",
  },
];

const roleLabels: Record<Role, string> = {
  dentist: "Hekim",
  patient: "Hasta",
  assistant_or_other: "Asistan / Diğer",
  unknown: "Bilinmiyor",
};

const statusLabels: Record<SpeakerStatus, string> = {
  clear: "Net",
  review_needed: "Onay gerekli",
  unresolved: "Çözülemedi",
};

const checklistLabels: Record<ChecklistState, string> = {
  found: "Var",
  review: "İncele",
  missing: "Eksik",
};

const procedureConditionColors: Record<string, string> = {
  kanal_tedavisi: "#7A5A8C",
  kompozit_dolgu: "#5A96C8",
  dis_cekimi: "#D8DDE5",
  gecici_restorasyon: "#E49545",
  rct: "#7A5A8C",
  composite: "#5A96C8",
  missing: "#D8DDE5",
  caries: "#D4503A",
  amalgam: "#7A7A7A",
  inlay: "#88B4D0",
  onlay: "#6694B8",
  crown: "#E49545",
  implant: "#4A86C2",
  other: "#D4884A",
};

const transcriptLinePattern = /^([A-Za-zÇĞİÖŞÜçğıöşü0-9_-]+)\s*:\s*(.+)$/;
const perioSites: PerioSite[] = ["MB", "B", "DB", "ML", "L", "DL"];

export default function ReviewPage() {
  const [productMode, setProductMode] = useState<ProductMode>("clinical_notes");
  const [sessionId, setSessionId] = useState("golden-s1-ui");
  const [patientName, setPatientName] = useState("Demo Danışan");
  const [encounterAt, setEncounterAt] = useState(() => toDatetimeLocalValue(new Date()));
  const [transcriptText, setTranscriptText] = useState(sampleTranscript);
  const [conversationRecords, setConversationRecords] = useState<ConversationRecord[]>([]);
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [selectedCode, setSelectedCode] = useState("FIX-KANAL-2K");
  const [selectedProcedureIndex, setSelectedProcedureIndex] = useState(0);
  const [approved, setApproved] = useState(false);
  const [response, setResponse] = useState<PipelineReviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recordingState, setRecordingState] = useState<RecordingState>("idle");
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [lastRecordingDuration, setLastRecordingDuration] = useState(0);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [audioFileName, setAudioFileName] = useState<string | null>(null);
  const [audioMessage, setAudioMessage] = useState<string | null>(null);
  const [liveAsrState, setLiveAsrState] = useState<LiveAsrState>("idle");
  const [liveAsrInterim, setLiveAsrInterim] = useState("");
  const [liveAsrMessage, setLiveAsrMessage] = useState<string | null>(null);
  const [roleGateMessage, setRoleGateMessage] = useState<string | null>(null);
  const [exportPayload, setExportPayload] = useState<ExportPayload | null>(null);
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const [editableNote, setEditableNote] = useState<ClinicalNote | null>(null);
  const [perioDraft, setPerioDraft] = useState<PerioDraft | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<number | null>(null);
  const recordingStartedAtRef = useRef<number | null>(null);
  const speechRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const speechUtterancesRef = useRef<TranscriptUtterance[]>([]);

  const utterances = useMemo(() => parseTranscript(transcriptText), [transcriptText]);
  const transcriptDiagnostics = useMemo(() => inspectTranscript(transcriptText), [transcriptText]);
  const canAnalyzeTranscript = transcriptDiagnostics.utteranceCount > 0 && transcriptDiagnostics.invalidLines.length === 0;
  const needsManualSpeakerSplit = transcriptDiagnostics.utteranceCount > 1 && transcriptDiagnostics.speakerCount < 2;
  const displayedDuration = recordingState === "recording" ? recordingSeconds : lastRecordingDuration;

  useEffect(() => {
    setResponse(null);
    setExportPayload(null);
    setRoleGateMessage(null);
    setPerioDraft(null);
    setAudioMessage(null);
    setApproved(false);
    setEditableNote(null);
    setExportMessage(null);
  }, [productMode]);

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
      streamRef.current?.getTracks().forEach((track) => track.stop());
      speechRecognitionRef.current?.abort();
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  const dentistReview = response?.dentist_review ?? null;
  const displayedNote = editableNote ?? dentistReview?.note ?? null;
  const procedures = dentistReview?.procedures ?? [];
  const activeProcedure = procedures[selectedProcedureIndex] ?? procedures[0] ?? null;
  const noteSections = displayedNote
    ? noteSectionsFromBackend(displayedNote)
    : [];
  const checklist = activeProcedure?.match_results[0]?.checklist ?? [];
  const candidateCodes = activeProcedure?.candidates.map((candidate) => candidate.code) ?? [];
  const activeTooth = activeProcedure?.procedure.tooth_number_fdi ?? 46;
  const activeProcedureLabel = activeProcedure
    ? procedureLabel(activeProcedure.procedure.procedure_family)
    : "Kanal";
  const procedureStatus = activeProcedure?.procedure.status ?? "planned";
  const canalStatus = activeProcedure?.procedure.canal_count ?? "unclear";
  const needsRoleReview = response?.next_action === "review_speaker_roles";
  const hasAnalysisDraft = response?.next_action === "review_note_and_codes" && Boolean(displayedNote);
  const issueCount = checklist.filter((item) => item.status !== "found").length +
    speakers.filter((speaker) => speaker.status !== "clear").length;
  const completedChecklist = checklist.filter((item) => item.status === "found").length;
  const perioFilledSites = perioDraft?.teeth.reduce(
    (total, tooth) => total + perioSites.filter((site) => tooth.sites[site].pocket !== undefined).length,
    0,
  ) ?? 0;

  const reviewState = approved
    ? "Onaylandı"
    : isLoading
      ? "Çalışıyor"
      : productMode === "perio_dictation"
        ? "Perio dikte"
      : needsRoleReview
        ? "Rol onayı"
        : "Klinik review";
  const meetingButtonLabel = recordingState === "recording"
    ? productMode === "perio_dictation" ? "Dikteyi Bitir" : "Görüşmeyi Bitir"
    : isLoading
      ? "Taslak Hazırlanıyor"
      : productMode === "perio_dictation" ? "Dikteyi Başlat" : "Görüşmeyi Başlat";

  function startNewConversation() {
    const now = new Date();
    setSessionId(`session-${now.getTime()}`);
    setPatientName("");
    setEncounterAt(toDatetimeLocalValue(now));
    setTranscriptText("");
    setSpeakers([]);
    setResponse(null);
    setEditableNote(null);
    setExportPayload(null);
    setExportMessage(null);
    setRoleGateMessage(null);
    setAudioMessage(null);
    setError(null);
    setApproved(false);
    setLastRecordingDuration(0);
    setRecordingSeconds(0);
    setSelectedProcedureIndex(0);
  }

  function loadConversationRecord(record: ConversationRecord) {
    setSessionId(record.id);
    setPatientName(record.patientName);
    setEncounterAt(record.encounterAt);
    setTranscriptText(record.transcriptText);
    setLastRecordingDuration(record.durationSec);
    setAudioMessage("Kayıt özeti yüklendi. Gerekiyorsa transkripti yeniden analiz edin.");
    setRoleGateMessage(null);
    setError(null);
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
    setExportMessage(null);
    setRoleGateMessage(null);
    setSelectedProcedureIndex(0);
    try {
      const result = await runTranscriptAnalysis(utterances);
      applyBackendResponse(result, utterances);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setIsLoading(false);
    }
  }

  async function analyzeRecognizedUtterances(sourceUtterances: TranscriptUtterance[]) {
    if (!sourceUtterances.length) {
      setLiveAsrMessage("Konuşma algılanmadı; tekrar deneyin.");
      return;
    }
    setIsLoading(true);
    setError(null);
    setApproved(false);
    setExportPayload(null);
    setEditableNote(null);
    setExportMessage(null);
    setRoleGateMessage(null);
    setSelectedProcedureIndex(0);
    try {
      const reviewResult = await runTranscriptAnalysis(sourceUtterances);
      applyBackendResponse(reviewResult, sourceUtterances);
      setLiveAsrMessage(
        reviewResult.next_action === "review_note_and_codes"
          ? "Canlı transcript analiz edildi; klinik review hazır."
          : "Canlı transcript analiz edildi; rol onayı bekliyor.",
      );
    } catch (caught) {
      setError(errorMessage(caught));
      setLiveAsrMessage("Canlı transcript alındı, analiz tamamlanamadı.");
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
    setRoleGateMessage(null);
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
      setSelectedProcedureIndex(0);
      setRoleGateMessage("Hekim rol onayı kaydedildi; klinik review hazır.");
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

  async function startRecording() {
    if (typeof window === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setError("Bu tarayıcıda mikrofon kaydı desteklenmiyor.");
      setAudioMessage("Mikrofon desteklenmiyor. Ses dosyası seçerek gerçek ASR akışını test edebilirsiniz.");
      return;
    }
    setError(null);
    setAudioMessage("Mikrofon izni bekleniyor. Tarayıcı sorarsa izin verin.");
    setAudioBlob(null);
    setAudioFileName(null);
    let stream: MediaStream;
    try {
      stream = await withTimeout(
        navigator.mediaDevices.getUserMedia({ audio: true }),
        12000,
        "Mikrofon izni zaman aşımına uğradı. Tarayıcı izinlerini kontrol edin ya da ses dosyası seçin.",
      );
    } catch (caught) {
      setError(errorMessage(caught));
      setAudioMessage("Mikrofon kaydı başlatılamadı. Ses dosyası seçerek devam edebilirsiniz.");
      setRecordingState("idle");
      return;
    }
    if (typeof MediaRecorder === "undefined") {
      stream.getTracks().forEach((track) => track.stop());
      setError("Bu tarayıcı MediaRecorder kaydını desteklemiyor.");
      setAudioMessage("Ses dosyası seçerek gerçek ASR akışını test edebilirsiniz.");
      return;
    }
    const recorder = new MediaRecorder(stream);
    chunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = () => {
      const durationSec = recordingStartedAtRef.current
        ? Math.max(1, Math.round((Date.now() - recordingStartedAtRef.current) / 1000))
        : recordingSeconds;
      setLastRecordingDuration(durationSec);
      recordingStartedAtRef.current = null;
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      setAudioBlob(blob);
      setAudioUrl(URL.createObjectURL(blob));
      setAudioFileName("mikrofon-kaydi.webm");
      setRecordingState("ready");
      setAudioMessage("Görüşme kaydı alındı. Taslak hazırlanıyor.");
      stream.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      void uploadAudioBlob(blob, "mikrofon-kaydi.webm");
    };
    streamRef.current = stream;
    recorderRef.current = recorder;
    recorder.start();
    recordingStartedAtRef.current = Date.now();
    setRecordingSeconds(0);
    setLastRecordingDuration(0);
    setAudioMessage(null);
    setRecordingState("recording");
    if (timerRef.current !== null) window.clearInterval(timerRef.current);
    timerRef.current = window.setInterval(() => {
      setRecordingSeconds((seconds) => seconds + 1);
    }, 1000);
  }

  function stopRecording() {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    recorderRef.current?.stop();
    recorderRef.current = null;
  }

  function toggleMeetingRecording() {
    if (recordingState === "recording") {
      stopRecording();
      return;
    }
    void startRecording();
  }

  function handleAudioFileSelection(file: File | null) {
    if (!file) return;
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioBlob(file);
    setAudioUrl(URL.createObjectURL(file));
    setAudioFileName(file.name);
    setRecordingState("ready");
    setAudioMessage("Ses dosyası alındı. Taslak hazırlanıyor.");
    setError(null);
    void uploadAudioBlob(file, file.name);
  }

  function startLiveAsr() {
    if (typeof window === "undefined") return;
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Recognition) {
      setError("Bu tarayıcı canlı konuşma tanımayı desteklemiyor. Demo için Chrome kullanın.");
      return;
    }

    speechRecognitionRef.current?.abort();
    const recognition = new Recognition();
    speechRecognitionRef.current = recognition;
    speechUtterancesRef.current = [];
    setTranscriptText("");
    setLiveAsrInterim("");
    setLiveAsrMessage("Dinleniyor; Türkçe klinik ifadelerinizi söyleyin.");
    setError(null);
    setApproved(false);
    setExportPayload(null);
    setRoleGateMessage(null);

    recognition.lang = "tr-TR";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      let interim = "";
      const finalTexts: string[] = [];
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const text = result[0]?.transcript.trim();
        if (!text) continue;
        if (result.isFinal) finalTexts.push(text);
        else interim += `${text} `;
      }
      if (finalTexts.length) {
        const nextUtterances = [
          ...speechUtterancesRef.current,
          ...finalTexts.map((text) => ({ speaker_id: "A", text })),
        ];
        speechUtterancesRef.current = nextUtterances;
        setTranscriptText(formatTranscript(nextUtterances));
      }
      setLiveAsrInterim(interim.trim());
    };
    recognition.onerror = (event) => {
      const reason = event.error ? ` (${event.error})` : "";
      setError(
        `Canlı ASR tarayıcı tarafından durduruldu${reason}. Demo için Kaydet → Durdur → Gerçek ASR veya Ses Dosyası akışını kullanın.`,
      );
      setLiveAsrMessage("Canlı ASR opsiyonel tarayıcı özelliğidir; gerçek analiz akışı kayıt dosyası üzerinden çalışır.");
      setLiveAsrState("idle");
    };
    recognition.onend = () => {
      setLiveAsrState("idle");
      setLiveAsrInterim("");
    };

    try {
      recognition.start();
      setLiveAsrState("listening");
    } catch {
      setError("Canlı ASR başlatılamadı. Demo için Kaydet → Durdur → Gerçek ASR akışını kullanın.");
      setLiveAsrMessage("Gerçek ASR için mikrofon kaydı veya ses dosyası yeterlidir.");
      setLiveAsrState("idle");
    }
  }

  function stopLiveAsrAndAnalyze() {
    speechRecognitionRef.current?.stop();
    setLiveAsrState("idle");
    setLiveAsrInterim("");
    void analyzeRecognizedUtterances(speechUtterancesRef.current);
  }

  function applyRoleTaggedSpeakerSplit() {
    const normalized = splitRoleTaggedTranscript(transcriptText);
    if (normalized === transcriptText) {
      setAudioMessage("Doktor:/Hasta:/Asistan: etiketi bulunamadı. Satır başlarını elle A:/B:/C: olarak düzeltip Analiz'e basın.");
      return;
    }
    setTranscriptText(normalized);
    setAudioMessage("Doktor/Hasta etiketleri A/B satırlarına çevrildi. Düzeltilmiş transkripti analiz edin.");
    setRoleGateMessage(null);
  }

  function updateTranscriptUtterance(index: number, patch: Partial<TranscriptUtterance>) {
    const updated = utterances.map((utterance, utteranceIndex) =>
      utteranceIndex === index ? { ...utterance, ...patch } : utterance,
    );
    setTranscriptText(formatTranscript(updated));
    setRoleGateMessage(null);
    setApproved(false);
    setExportPayload(null);
  }

  async function uploadAudioBlob(sourceBlob: Blob, sourceFileName: string) {
    setIsLoading(true);
    setError(null);
    setAudioMessage("Ses işleniyor; transkript ve klinik taslak hazırlanıyor.");
    setRoleGateMessage(null);
    setExportPayload(null);
    try {
      const form = new FormData();
      form.append("audio", sourceBlob, sourceFileName);
      const reviewResult = await postReviewFormResponse(`/sessions/${encodeURIComponent(sessionId)}/audio`, form);
      const result = reviewResult.audio_processing;
      if (!result) {
        setAudioMessage("Ses endpoint'i audio_processing sonucu döndürmedi.");
        return;
      }
      let analysisMessage = "";
      if (result.transcript?.utterances.length) {
        const transcriptUtterances = result.transcript.utterances;
        const speakerCount = new Set(transcriptUtterances.map((utterance) => utterance.speaker_id)).size;
        setTranscriptText(formatTranscript(transcriptUtterances));
        if (productMode === "perio_dictation") {
          const draft = buildPerioDraftFromTranscript(transcriptUtterances);
          setPerioDraft(draft);
          setResponse(null);
          setRoleGateMessage(
            draft.review_items.length
              ? "Perio taslak hazır. İnceleme gerektiren bölgeler işaretlendi."
              : "Perio taslak hazır. Hekim gözden geçirip onaylayabilir.",
          );
          analysisMessage = ` · ${speakerCount} konuşmacı algılandı · ${draft.teeth.length} diş perio taslağına işlendi`;
        } else {
          applyBackendResponse(reviewResult, transcriptUtterances);
          if (speakerCount < 2) {
            setRoleGateMessage("Deepgram tek konuşmacı algıladı. Transkript satırlarını A:/B: olarak düzeltip yeniden Analiz çalıştırın.");
          } else if (reviewResult.next_action === "review_speaker_roles") {
            setRoleGateMessage("Transkript hazır. Klinik not ve işlem analizi için konuşmacı rollerini onaylayın.");
          } else {
            setRoleGateMessage(null);
          }
          analysisMessage =
            reviewResult.next_action === "review_note_and_codes"
              ? ` · ${speakerCount} konuşmacı algılandı · klinik review hazır`
              : ` · ${speakerCount} konuşmacı algılandı · rol onayı bekliyor`;
        }
      }
      const warningsText = result.warnings?.length ? ` · uyarı: ${result.warnings.join(" · ")}` : "";
      setAudioMessage(
        `${result.status} · provider: ${result.provider_status} · ham ses silindi: ${result.raw_audio_deleted ? "evet" : "hayır"}${analysisMessage} · ${result.message}${warningsText}`,
      );
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
    upsertConversationRecord(result, sourceUtterances);
  }

  function upsertConversationRecord(result: PipelineReviewResponse, sourceUtterances: TranscriptUtterance[]) {
    const normalizedTranscript = formatTranscript(sourceUtterances);
    const record: ConversationRecord = {
      id: result.session_id || sessionId,
      patientName: patientName.trim() || "İsimsiz danışan",
      encounterAt,
      durationSec: displayedDuration,
      transcriptText: normalizedTranscript,
      utteranceCount: sourceUtterances.length,
      speakerCount: new Set(sourceUtterances.map((utterance) => utterance.speaker_id)).size,
      status: statusText(result.status),
      nextAction: result.next_action,
      noteSectionCount: result.dentist_review?.note ? noteSectionsFromBackend(result.dentist_review.note).filter((section) => section.lines.length).length : 0,
      procedureCount: result.dentist_review?.procedures.length ?? 0,
    };
    setConversationRecords((current) => {
      const next = [record, ...current.filter((item) => item.id !== record.id)];
      return next.slice(0, 8);
    });
  }

  function updateSpeakerRole(id: string, role: Role) {
    setSpeakers((current) =>
      current.map((speaker) =>
        speaker.id === id ? { ...speaker, role, status: "clear" } : speaker,
      ),
    );
  }

  function updateNoteSentence(sectionId: NoteSectionId, lineIndex: number, text: string) {
    setEditableNote((current) => {
      if (!current) return current;
      const section = current[sectionId];
      return {
        ...current,
        [sectionId]: section.map((sentence, index) =>
          index === lineIndex ? { ...sentence, text } : sentence,
        ),
      };
    });
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

  function printExportAsPdf() {
    if (!exportPayload) return;
    const printWindow = window.open("", "_blank", "noopener,noreferrer");
    if (!printWindow) {
      setExportMessage("PDF yazdırma penceresi açılamadı.");
      return;
    }
    printWindow.document.write(`
      <html>
        <head>
          <title>${escapeHtml(exportPayload.session_id)} Tandela Export</title>
          <style>
            body { font-family: Arial, sans-serif; padding: 32px; color: #202422; }
            pre { white-space: pre-wrap; font-size: 13px; line-height: 1.6; }
          </style>
        </head>
        <body>
          <pre>${escapeHtml(formatExportPayload(exportPayload))}</pre>
        </body>
      </html>
    `);
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
    setExportMessage("PDF için tarayıcı yazdırma penceresi açıldı.");
  }

  return (
    <main className="min-h-screen bg-[#f4f6f4] text-ink">
      <header className="sticky top-0 z-20 border-b border-black/10 bg-white/92 backdrop-blur">
        <div className="mx-auto flex max-w-[1540px] flex-wrap items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-[8px] bg-ink text-white">
              <Mic2 className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
                <p className="text-sm font-semibold text-muted">Tandela TR</p>
              <h1 className="text-xl font-semibold tracking-normal">Klinik Review Workspace</h1>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={reviewState} tone={needsRoleReview ? "warning" : "success"} loading={isLoading} />
            <button
              className="inline-flex h-10 items-center gap-2 rounded-[8px] border border-black/10 bg-white px-3 text-sm font-semibold shadow-line disabled:opacity-55"
              type="button"
              onClick={() => void analyzeTranscript()}
              disabled={isLoading || !canAnalyzeTranscript}
              title="Transkripti analiz et"
            >
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              Analiz
            </button>
            <button
              className="inline-flex h-10 items-center gap-2 rounded-[8px] bg-teal px-3 text-sm font-semibold text-white shadow-line disabled:opacity-55"
              type="button"
              onClick={() => void approveRolesAndResume()}
              disabled={isLoading || !needsRoleReview || !canAnalyzeTranscript}
              title="Rolleri onayla"
            >
              <Play className="h-4 w-4" aria-hidden="true" />
              Rolleri Onayla
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1540px] gap-4 px-4 py-4 pb-24 sm:px-6 lg:grid-cols-[300px_minmax(0,1fr)_420px] lg:px-8">
        <aside className="grid content-start gap-4">
          <section className="rounded-[8px] border border-black/10 bg-white p-4 shadow-line">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">Görüşme</p>
                <input
                  className="mt-2 h-10 w-full rounded-[8px] border border-black/10 bg-linen px-3 text-sm font-semibold"
                  value={patientName}
                  onChange={(event) => setPatientName(event.target.value)}
                  placeholder="Danışan adı"
                  aria-label="Danışan adı"
                />
              </div>
              <button
                className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-[8px] bg-linen text-ink"
                type="button"
                onClick={startNewConversation}
                title="Yeni görüşme"
              >
                <FileText className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <div className="mt-3 grid gap-2">
              <label className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">
                Tarih
                <input
                  className="mt-1 h-10 w-full rounded-[8px] border border-black/10 bg-linen px-3 text-sm font-semibold normal-case tracking-normal text-ink"
                  type="datetime-local"
                  value={encounterAt}
                  onChange={(event) => setEncounterAt(event.target.value)}
                  aria-label="Görüşme tarihi"
                />
              </label>
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">Session ID</p>
                <input
                  className="mt-2 h-10 w-full rounded-[8px] border border-black/10 bg-linen px-3 text-sm font-semibold"
                  value={sessionId}
                  onChange={(event) => setSessionId(event.target.value)}
                  aria-label="Session ID"
                />
              </div>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2 text-sm">
              <Metric label="Süre" value={formatDuration(displayedDuration)} />
              <Metric label="İfade" value={`${transcriptDiagnostics.utteranceCount}`} />
              <Metric label="Uyarı" value={productMode === "perio_dictation" ? `${perioDraft?.review_items.length ?? 0}` : `${issueCount}`} />
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <button
                className={`rounded-[8px] border px-3 py-2 text-sm font-semibold ${
                  productMode === "clinical_notes" ? "border-teal bg-teal text-white" : "border-black/10 bg-linen text-ink"
                }`}
                type="button"
                onClick={() => setProductMode("clinical_notes")}
              >
                Hasta görüşmesi
              </button>
              <button
                className={`rounded-[8px] border px-3 py-2 text-sm font-semibold ${
                  productMode === "perio_dictation" ? "border-teal bg-teal text-white" : "border-black/10 bg-linen text-ink"
                }`}
                type="button"
                onClick={() => setProductMode("perio_dictation")}
              >
                Perio dikte
              </button>
            </div>
          </section>

          <section className="rounded-[8px] border border-black/10 bg-white p-4 shadow-line">
            <div className="flex items-center gap-2">
              <History className="h-5 w-5 text-moss" aria-hidden="true" />
              <h2 className="text-lg font-semibold">Görüşme kayıtları</h2>
            </div>
            <div className="mt-4 grid gap-3">
              {conversationRecords.length ? (
                conversationRecords.map((record) => (
                  <button
                    key={record.id}
                    className="rounded-[8px] border border-black/10 bg-linen p-3 text-left hover:border-teal/50"
                    type="button"
                    onClick={() => loadConversationRecord(record)}
                    title="Görüşme kaydını aç"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-semibold">{record.patientName}</p>
                        <p className="mt-1 text-xs font-semibold text-muted">{formatEncounterDate(record.encounterAt)}</p>
                      </div>
                      <span className="shrink-0 rounded-[8px] bg-white px-2 py-1 text-xs font-semibold text-muted">
                        {formatDuration(record.durationSec)}
                      </span>
                    </div>
                    <div className="mt-3 grid grid-cols-3 gap-2 text-xs font-semibold text-muted">
                      <span>{record.utteranceCount} ifade</span>
                      <span>{record.speakerCount} konuşmacı</span>
                      <span>{record.procedureCount} işlem</span>
                    </div>
                    <p className="mt-2 truncate text-xs font-semibold text-teal">{record.status}</p>
                  </button>
                ))
              ) : (
                <p className="rounded-[8px] bg-linen p-3 text-sm font-semibold leading-6 text-muted">
                  Henüz kayıt yok. Analiz çalışınca görüşme burada listelenir.
                </p>
              )}
            </div>
          </section>

          <section className="rounded-[8px] border border-black/10 bg-white p-4 shadow-line">
            <div className="flex items-center gap-2">
              <ClipboardList className="h-5 w-5 text-moss" aria-hidden="true" />
              <h2 className="text-lg font-semibold">Transkript</h2>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2 text-xs font-semibold text-muted">
              <span>İfade: {transcriptDiagnostics.utteranceCount}</span>
              <span>Konuşmacı: {transcriptDiagnostics.speakerCount}</span>
              <span>Hata: {transcriptDiagnostics.invalidLines.length}</span>
            </div>
            {utterances.length ? (
              <div className="mt-4 grid max-h-[360px] gap-2 overflow-auto pr-1">
                {utterances.map((utterance, index) => (
                  <div key={`${index}-${utterance.text.slice(0, 18)}`} className="rounded-[8px] border border-black/10 bg-linen/70 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-[8px] bg-white text-xs font-semibold shadow-line">
                        {index + 1}
                      </span>
                      <select
                        className="h-8 min-w-[132px] rounded-[8px] border border-black/10 bg-white px-2 text-xs font-semibold text-ink"
                        value={utterance.speaker_id}
                        onChange={(event) => updateTranscriptUtterance(index, { speaker_id: event.target.value })}
                        aria-label={`${index + 1}. ifade konuşmacısı`}
                      >
                        <option value="A">Hekim · A</option>
                        <option value="B">Hasta · B</option>
                        <option value="C">Asistan · C</option>
                        <option value="D">Diğer · D</option>
                      </select>
                    </div>
                    <textarea
                      className="mt-2 min-h-[74px] w-full resize-y rounded-[8px] border border-black/10 bg-white p-2 text-sm leading-6 text-ink"
                      value={utterance.text}
                      onChange={(event) => updateTranscriptUtterance(index, { text: event.target.value })}
                      aria-label={`${index + 1}. ifade metni`}
                    />
                  </div>
                ))}
              </div>
            ) : null}
            <textarea
              className={`mt-4 min-h-[180px] w-full resize-y rounded-[8px] border p-3 text-sm leading-6 text-ink ${
                transcriptDiagnostics.invalidLines.length
                  ? "border-coral/50 bg-coral/5"
                  : "border-black/10 bg-linen"
              }`}
              value={transcriptText}
              onChange={(event) => setTranscriptText(event.target.value)}
              aria-label="Transkript"
            />
            {transcriptDiagnostics.invalidLines.length ? (
              <p className="mt-3 rounded-[8px] bg-coral/10 p-3 text-xs font-semibold leading-5 text-coral">
                Satır {transcriptDiagnostics.invalidLines.join(", ")} okunamadı. Her ifade A: metin formatında olmalı.
              </p>
            ) : needsManualSpeakerSplit ? (
              <p className="mt-3 rounded-[8px] bg-gold/18 p-3 text-xs font-semibold leading-5 text-[#7a6221]">
                Tek konuşmacı algılandı. Hekim ve hasta aynı A satırında kaldıysa satır editoründe ifadeleri Hekim/Hasta olarak ayırıp yeniden analiz edin.
              </p>
            ) : (
              <p className="mt-3 text-xs font-semibold text-muted">
                Düzenlenen transkript analiz edilecek.
              </p>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                className="inline-flex h-9 items-center gap-2 rounded-[8px] border border-black/10 bg-white px-3 text-xs font-semibold"
                type="button"
                onClick={() => setTranscriptText(sampleTranscript)}
                title="Örnek transkripti yükle"
              >
                <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                Örneği Yükle
              </button>
              <button
                className="inline-flex h-9 items-center gap-2 rounded-[8px] border border-black/10 bg-white px-3 text-xs font-semibold"
                type="button"
                onClick={() => setTranscriptText(formatTranscript(utterances))}
                disabled={!utterances.length}
                title="Geçerli satırları yeniden biçimlendir"
              >
                <ListChecks className="h-3.5 w-3.5" aria-hidden="true" />
                Biçimle
              </button>
              <button
                className="inline-flex h-9 items-center gap-2 rounded-[8px] border border-black/10 bg-white px-3 text-xs font-semibold"
                type="button"
                onClick={applyRoleTaggedSpeakerSplit}
                title="Doktor:/Hasta: etiketlerini A:/B: satırlarına çevir"
              >
                <UserCheck className="h-3.5 w-3.5" aria-hidden="true" />
                Doktor/Hasta → A/B
              </button>
              <button
                className="inline-flex h-9 items-center gap-2 rounded-[8px] bg-ink px-3 text-xs font-semibold text-white disabled:opacity-55"
                type="button"
                onClick={() => void analyzeTranscript()}
                disabled={isLoading || !canAnalyzeTranscript}
                title="Düzeltilmiş transkripti analiz et"
              >
                <Play className="h-3.5 w-3.5" aria-hidden="true" />
                Düzeltilmiş Analiz
              </button>
            </div>
          </section>

          <section className="rounded-[8px] border border-black/10 bg-white p-4 shadow-line">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">
                  {productMode === "perio_dictation" ? "Dikte" : "Hasta toplantısı"}
                </p>
                <h2 className="mt-1 text-lg font-semibold">
                  {productMode === "perio_dictation" ? "Perio kaydı" : "Görüşme kaydı"}
                </h2>
              </div>
              <Mic2 className="h-5 w-5 text-teal" aria-hidden="true" />
            </div>
            <p className="mt-3 text-sm leading-6 text-muted">
              {productMode === "perio_dictation"
                ? "Muayene sırasında cep derinliği, kanama, plak ve furkasyon değerlerini sesli dikte edin. Kayıt bitince perio chart taslağı hazırlanır."
                : "Hastayla her zamanki gibi konuşun. Görüşmeyi bitirdiğinizde klinik not, dental chart ve perio chart taslakları inceleme için hazırlanır."}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                className="inline-flex h-10 items-center gap-2 rounded-[8px] bg-teal px-3 text-sm font-semibold text-white disabled:opacity-55"
                type="button"
                onClick={toggleMeetingRecording}
                disabled={isLoading}
                title={recordingState === "recording" ? "Görüşmeyi bitir ve taslağı oluştur" : "Hasta görüşmesini başlat"}
              >
                {recordingState === "recording" ? <Square className="h-4 w-4" aria-hidden="true" /> : <Mic2 className="h-4 w-4" aria-hidden="true" />}
                {meetingButtonLabel}
              </button>
              <label
                className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-[8px] border border-black/10 bg-white px-3 text-sm font-semibold"
                title="Hazır ses dosyası seç ve taslak oluştur"
              >
                <Upload className="h-4 w-4" aria-hidden="true" />
                Ses Dosyası
                <input
                  className="sr-only"
                  type="file"
                  accept="audio/*,.webm,.wav,.mp3,.m4a,.aiff,.aif"
                  onChange={(event) => handleAudioFileSelection(event.target.files?.[0] ?? null)}
                />
              </label>
            </div>
            <div className="mt-4 rounded-[8px] bg-linen p-3 text-sm font-semibold text-muted">
              Durum: {recordingState === "recording" ? `Kayıtta · ${recordingSeconds}s` : recordingState === "ready" ? `Kayıt hazır${audioFileName ? ` · ${audioFileName}` : ""}` : "Beklemede"}
            </div>
            {audioUrl ? (
              <audio className="mt-3 w-full" controls src={audioUrl} />
            ) : null}
            {audioMessage ? (
              <p className="mt-3 rounded-[8px] bg-teal/10 p-3 text-sm font-semibold leading-6 text-teal">
                {audioMessage}
              </p>
            ) : null}
            {roleGateMessage ? (
              <p className="mt-3 rounded-[8px] bg-gold/18 p-3 text-sm font-semibold leading-6 text-[#7a6221]">
                {roleGateMessage}
              </p>
            ) : null}
          </section>
        </aside>

        <section className="rounded-[8px] border border-black/10 bg-white shadow-line">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-black/10 p-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">Draft note</p>
              <h2 className="mt-1 text-2xl font-semibold">{activeTooth} {activeProcedureLabel} Review</h2>
            </div>
            <button
              className="inline-flex items-center gap-3 rounded-[8px] border border-black/10 bg-linen px-4 py-3 text-sm font-semibold"
              type="button"
              title="Not tipi"
            >
              <FileText className="h-5 w-5 text-muted" aria-hidden="true" />
              Kapsamlı
              <ChevronDown className="h-4 w-4 text-muted" aria-hidden="true" />
            </button>
          </div>

          {error ? (
            <div className="mx-4 mt-4 rounded-[8px] border border-coral/30 bg-coral/10 p-4 text-sm font-semibold text-coral">
              {error}
            </div>
          ) : null}

          <div className="grid gap-6 p-4 lg:p-6">
            <section className="rounded-[8px] border border-black/10 bg-paper p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 text-muted">
                    <CalendarClock className="h-4 w-4" aria-hidden="true" />
                    <p className="text-xs font-semibold uppercase tracking-[0.14em]">Görüşme özeti</p>
                  </div>
                  <h3 className="mt-1 text-xl font-semibold">{patientName.trim() || "İsimsiz danışan"}</h3>
                  <p className="mt-2 text-sm font-semibold leading-6 text-muted">
                    {formatEncounterDate(encounterAt)} · {formatDuration(displayedDuration)} · {transcriptDiagnostics.utteranceCount} ifade · {transcriptDiagnostics.speakerCount} konuşmacı
                  </p>
                </div>
                <StatusBadge label={response?.status ? statusText(response.status) : "Taslak"} tone={needsRoleReview ? "warning" : "success"} loading={isLoading} />
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <Metric label="Transkript" value={`${transcriptDiagnostics.utteranceCount}`} />
                <Metric label="Not başlığı" value={`${noteSections.filter((section) => section.lines.length).length}`} />
                <Metric label="İşlem" value={`${procedures.length}`} />
              </div>
            </section>

            <section className="grid gap-3 lg:grid-cols-3">
              <ProductOutputCard
                index="01"
                title="Clinical-note drafts"
                subtitle="Ana şikayet, geçmiş, bulgular ve tedavi planı"
                status={displayedNote ? "Taslak hazır" : "Bekliyor"}
                tone={displayedNote ? "success" : "neutral"}
                icon={<FileText className="h-5 w-5" aria-hidden="true" />}
              />
              <ProductOutputCard
                index="02"
                title="Dental chart"
                subtitle={`${activeTooth} diş bulgusu ve işlem etiketi`}
                status={activeProcedure ? "Chart taslağı" : "Bekliyor"}
                tone={activeProcedure ? "success" : "neutral"}
                icon={<CircleDot className="h-5 w-5" aria-hidden="true" />}
              />
              <ProductOutputCard
                index="03"
                title="Perio charting"
                subtitle="Cep, kanama, plak, furkasyon ve mobilite"
                status={perioDraft?.teeth.length ? "Perio taslak" : "Dikte bekliyor"}
                tone={perioDraft?.teeth.length ? "success" : "neutral"}
                icon={<ClipboardList className="h-5 w-5" aria-hidden="true" />}
              />
            </section>

            <div className="grid gap-3 sm:grid-cols-3">
              {productMode === "perio_dictation" ? (
                <>
                  <Metric label="Diş" value={`${perioDraft?.teeth.length ?? 0}`} />
                  <Metric label="Bölge" value={`${perioFilledSites}`} />
                  <Metric label="İncele" value={`${perioDraft?.review_items.length ?? 0}`} />
                </>
              ) : (
                <>
                  <Metric label="Kaynak" value={response?.next_action ?? "Hazır"} />
                  <Metric label="Durum" value={statusText(response?.status)} />
                  <Metric label="Checklist" value={`${completedChecklist}/${checklist.length}`} />
                </>
              )}
            </div>

            {productMode === "perio_dictation" ? (
              <PerioDraftPanel draft={perioDraft} isLoading={isLoading} />
            ) : (
              <>
            {needsRoleReview ? (
              <section className="rounded-[8px] border border-gold/30 bg-gold/10 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#7a6221]">Analiz bekliyor</p>
                    <h3 className="mt-1 text-lg font-semibold text-[#7a6221]">Konuşmacı rollerini onaylayın</h3>
                    <p className="mt-2 text-sm font-semibold leading-6 text-[#7a6221]">
                      Transkript alındı. Klinik not, işlem kodları ve dental chart rol onayından sonra oluşturulacak.
                    </p>
                    {needsManualSpeakerSplit ? (
                      <p className="mt-2 rounded-[8px] bg-white/70 p-3 text-sm font-semibold leading-6 text-[#7a6221]">
                        Şu anda transkriptte tek konuşmacı var. Aynı konuşmacıya hem hekim hem hasta rolü verilemez; sol taraftaki satır editoründe ifadeleri Hekim/Hasta olarak ayırıp Düzeltilmiş Analiz çalıştırın.
                      </p>
                    ) : null}
                  </div>
                  <button
                    className="inline-flex h-11 items-center gap-2 rounded-[8px] bg-ink px-4 text-sm font-semibold text-white disabled:opacity-55"
                    type="button"
                    onClick={() => void approveRolesAndResume()}
                    disabled={isLoading || !canAnalyzeTranscript}
                    title="Rolleri onayla ve analizi oluştur"
                  >
                    <UserCheck className="h-4 w-4" aria-hidden="true" />
                    Rolleri Onayla ve Analizi Oluştur
                  </button>
                </div>
              </section>
            ) : null}

            {hasAnalysisDraft ? (
              <div className="grid gap-5">
              {noteSections.map((section) => (
                <section key={section.title} className="rounded-[8px] border border-black/10 bg-paper p-4">
                  <h3 className="text-lg font-semibold">{section.title}</h3>
                  <div className="mt-3 space-y-3 text-base leading-7 text-[#555a56]">
                    {section.lines.length ? (
                      section.lines.map((line, lineIndex) => (
                        <div key={`${section.id}-${lineIndex}`}>
                          <textarea
                            className="min-h-[72px] w-full resize-y rounded-[8px] border border-black/10 bg-white p-3 text-sm leading-6 text-ink"
                            value={line.text}
                            onChange={(event) => updateNoteSentence(section.id, lineIndex, event.target.value)}
                            aria-label={`${section.title} taslak cümlesi`}
                          />
                          {line.source_quote ? (
                            <p className="mt-1 text-xs font-semibold leading-5 text-muted">
                              {roleLabels[line.source_role ?? "unknown"]}: {line.source_quote}
                            </p>
                          ) : null}
                        </div>
                      ))
                    ) : (
                      <p className="text-muted/70">Kayıt yok.</p>
                    )}
                  </div>
                </section>
              ))}
              </div>
            ) : !response ? (
              <section className="rounded-[8px] border border-black/10 bg-paper p-4">
                <h3 className="text-lg font-semibold">Taslak bekleniyor</h3>
                <p className="mt-2 text-sm font-semibold leading-6 text-muted">
                  Transkripti kontrol edip Analiz düğmesine basın.
                </p>
              </section>
            ) : null}

            {dentistReview?.uncertain_items.length ? (
              <section className="rounded-[8px] border border-gold/30 bg-gold/10 p-4">
                <div className="flex items-center gap-2 text-[#7a6221]">
                  <AlertTriangle className="h-5 w-5" aria-hidden="true" />
                  <h3 className="text-lg font-semibold">Hekim kontrolü gerekenler</h3>
                </div>
                <div className="mt-3 grid gap-2 text-sm font-semibold leading-6 text-[#7a6221]">
                  {dentistReview.uncertain_items.map((item) => (
                    <p key={item}>{item}</p>
                  ))}
                </div>
              </section>
            ) : null}

            {exportPayload ? (
              <section className="rounded-[8px] border border-teal/25 bg-teal/8 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal">Export hazır</p>
                    <h3 className="mt-1 text-lg font-semibold">Onaylı çıktı</h3>
                  </div>
                  <StatusBadge label="Export" tone="success" />
                </div>
                <pre className="mt-4 max-h-[260px] overflow-auto whitespace-pre-wrap rounded-[8px] bg-white p-4 text-sm leading-6 text-ink shadow-line">
                  {formatExportPayload(exportPayload)}
                </pre>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    className="inline-flex h-10 items-center gap-2 rounded-[8px] bg-ink px-3 text-sm font-semibold text-white"
                    type="button"
                    onClick={() => void copyExportToClipboard()}
                    title="Export metnini kopyala"
                  >
                    <Copy className="h-4 w-4" aria-hidden="true" />
                    Kopyala
                  </button>
                  <button
                    className="inline-flex h-10 items-center gap-2 rounded-[8px] border border-black/10 bg-white px-3 text-sm font-semibold"
                    type="button"
                    onClick={downloadExportTxt}
                    title="TXT indir"
                  >
                    <Download className="h-4 w-4" aria-hidden="true" />
                    TXT
                  </button>
                  <button
                    className="inline-flex h-10 items-center gap-2 rounded-[8px] border border-black/10 bg-white px-3 text-sm font-semibold"
                    type="button"
                    onClick={printExportAsPdf}
                    title="PDF olarak yazdır"
                  >
                    <Printer className="h-4 w-4" aria-hidden="true" />
                    PDF
                  </button>
                </div>
                {exportMessage ? (
                  <p className="mt-3 text-sm font-semibold leading-6 text-teal">{exportMessage}</p>
                ) : null}
                <p className="mt-3 text-sm font-semibold leading-6 text-muted">{exportPayload.warning}</p>
              </section>
            ) : null}
              </>
            )}
          </div>
        </section>

        <aside className="grid content-start gap-4">
          <section className="rounded-[8px] border border-black/10 bg-white p-4 shadow-line">
            <PanelTitle index="01" title="Konuşmacı rolleri" icon={<UserCheck className="h-5 w-5" />} />
            <div className="mt-4 grid gap-3">
              {speakers.map((speaker) => (
                <div key={speaker.id} className="rounded-[8px] border border-black/10 bg-linen/60 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-[8px] bg-white font-semibold shadow-line">
                        {speaker.id}
                      </span>
                      <div className="min-w-0">
                        <p className="truncate font-semibold">{roleLabels[speaker.role]}</p>
                        <p className="text-sm text-muted">{speaker.utterances} ifade</p>
                      </div>
                    </div>
                    <StatusDot status={speaker.status} />
                  </div>
                  <p className="mt-3 text-sm leading-6 text-muted">{speaker.sample}</p>
                  {speaker.reason ? <p className="mt-2 text-xs leading-5 text-muted">{speaker.reason}</p> : null}
                  <select
                    className="mt-3 h-10 w-full rounded-[8px] border border-black/10 bg-white px-3 text-sm font-semibold text-ink"
                    value={speaker.role}
                    onChange={(event) => updateSpeakerRole(speaker.id, event.target.value as Role)}
                    aria-label={`${speaker.id} rolü`}
                  >
                    <option value="unknown">Bilinmiyor</option>
                    <option value="dentist">Hekim</option>
                    <option value="patient">Hasta</option>
                    <option value="assistant_or_other">Asistan / Diğer</option>
                  </select>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-[8px] border border-black/10 bg-white p-4 shadow-line">
            <PanelTitle index="02" title="Dental chart" icon={<CircleDot className="h-5 w-5" />} />
            <DentalChart procedures={procedures.map((procedure) => procedure.procedure)} approved={approved} />
          </section>

          <section className="rounded-[8px] border border-black/10 bg-white p-4 shadow-line">
            <PanelTitle index="03" title="Kod checklist" icon={<ListChecks className="h-5 w-5" />} />

            {activeProcedure ? (
              <div className="mt-4 rounded-[8px] bg-linen p-3">
                <div className="grid grid-cols-2 gap-2 text-sm font-semibold text-ink">
                  <span>İşlem: {procedureLabel(activeProcedure.procedure.procedure_family)}</span>
                  <span>Diş: {activeProcedure.procedure.tooth_number_fdi ?? "Belirsiz"}</span>
                  <span>Durum: {procedureStatusLabel(activeProcedure.procedure.status)}</span>
                  <span>Kanal: {activeProcedure.procedure.canal_count ?? "Belirsiz"}</span>
                </div>
                {activeProcedure.procedure.source_quotes.length ? (
                  <p className="mt-3 text-xs font-semibold leading-5 text-muted">
                    {activeProcedure.procedure.source_quotes[0]}
                  </p>
                ) : null}
              </div>
            ) : null}

            {procedures.length > 1 ? (
              <div className="mt-4 grid grid-cols-2 gap-2">
                {procedures.map((procedure, index) => (
                  <button
                    key={`${procedure.procedure.procedure_family}-${index}`}
                    className={`rounded-[8px] border px-3 py-2 text-sm font-semibold ${
                      selectedProcedureIndex === index
                        ? "border-teal bg-teal text-white"
                        : "border-black/10 bg-linen text-ink"
                    }`}
                    type="button"
                    onClick={() => setSelectedProcedureIndex(index)}
                  >
                    {procedureLabel(procedure.procedure.procedure_family)}
                  </button>
                ))}
              </div>
            ) : null}

            <div className="mt-4 grid grid-cols-3 gap-2">
              {candidateCodes.map((code) => (
                <button
                  key={code}
                  type="button"
                  title={code}
                  onClick={() => setSelectedCode(code)}
                  className={`min-h-10 rounded-[8px] border px-2 py-2 text-xs font-semibold sm:text-sm ${
                    selectedCode === code
                      ? "border-teal bg-teal text-white"
                      : "border-black/10 bg-linen text-ink"
                  }`}
                >
                  {code.replace("FIX-", "")}
                </button>
              ))}
            </div>

            <div className="mt-4 grid gap-3">
              {checklist.map((item) => (
                <div key={item.item_id} className="rounded-[8px] border border-black/10 bg-white p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold">{item.label}</p>
                      <p className="mt-1 text-sm leading-6 text-muted">{item.evidence_quote ?? "Kanıt yok"}</p>
                    </div>
                    <ChecklistPill state={item.status} />
                  </div>
                </div>
              ))}
            </div>

            {activeProcedure?.ambiguity_note ? (
              <p className="mt-4 rounded-[8px] bg-gold/12 p-3 text-sm font-semibold leading-6 text-[#7a6221]">
                {activeProcedure.ambiguity_note}
              </p>
            ) : null}

            <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-black/10 pt-4">
              <div className="text-sm font-semibold text-muted">
                {completedChecklist}/{checklist.length} madde tamam
              </div>
              <button
                type="button"
                title="Review onayla"
                onClick={() => void approveClinicalReview()}
                disabled={isLoading || !hasAnalysisDraft}
                className="inline-flex items-center gap-2 rounded-[8px] bg-ink px-4 py-3 text-sm font-semibold text-white disabled:opacity-55"
              >
                <Check className="h-4 w-4" aria-hidden="true" />
                Onayla
              </button>
            </div>
          </section>
        </aside>
      </div>

      <div className="fixed bottom-4 left-1/2 z-10 flex w-[calc(100%-32px)] max-w-xl -translate-x-1/2 items-center justify-between gap-3 rounded-[8px] border border-black/10 bg-white/94 px-4 py-3 shadow-soft backdrop-blur">
        <div className="flex min-w-0 items-center gap-3">
          <Mic2 className="h-5 w-5 shrink-0 text-teal" aria-hidden="true" />
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{patientName.trim() || "İsimsiz danışan"}</p>
            <p className="truncate text-xs text-muted">
              {formatEncounterDate(encounterAt)} · {formatDuration(displayedDuration)} · {response?.next_action ?? "hazır"}
            </p>
          </div>
        </div>
        <button
          type="button"
          title="Taslağı kaydet"
          className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-[8px] bg-linen text-ink"
        >
          <Save className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </main>
  );
}

function PanelTitle({ index, title, icon }: { index: string; title: string; icon: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <span className="text-2xl font-light text-black/18">{index}</span>
        <h2 className="text-xl font-semibold">{title}</h2>
      </div>
      <div className="text-teal">{icon}</div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[8px] border border-black/10 bg-white p-3 shadow-line">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}

function ProductOutputCard({
  index,
  title,
  subtitle,
  status,
  tone,
  icon,
}: {
  index: string;
  title: string;
  subtitle: string;
  status: string;
  tone: "success" | "neutral";
  icon: React.ReactNode;
}) {
  return (
    <div className="rounded-[8px] border border-black/10 bg-white p-4 shadow-line">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-2xl font-light text-black/18">{index}</p>
          <h3 className="mt-1 text-base font-semibold">{title}</h3>
        </div>
        <div className={tone === "success" ? "text-teal" : "text-muted"}>{icon}</div>
      </div>
      <p className="mt-3 min-h-10 text-sm font-semibold leading-5 text-muted">{subtitle}</p>
      <span
        className={`mt-4 inline-flex rounded-[8px] px-2.5 py-1 text-xs font-semibold ${
          tone === "success" ? "bg-teal/12 text-teal" : "bg-linen text-muted"
        }`}
      >
        {status}
      </span>
    </div>
  );
}

function StatusBadge({ label, tone, loading }: { label: string; tone: "success" | "warning"; loading?: boolean }) {
  return (
    <div
      className={`inline-flex h-10 items-center gap-2 rounded-[8px] px-3 text-sm font-semibold ${
        tone === "success" ? "bg-teal/12 text-teal" : "bg-gold/18 text-[#7a6221]"
      }`}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
      {label}
    </div>
  );
}

function StatusDot({ status }: { status: SpeakerStatus }) {
  return (
    <span
      className={`rounded-[8px] px-2.5 py-1 text-xs font-semibold ${
        status === "clear" ? "bg-teal/12 text-teal" : "bg-gold/18 text-[#7a6221]"
      }`}
    >
      {statusLabels[status]}
    </span>
  );
}

function ChecklistPill({ state }: { state: ChecklistState }) {
  const icon = state === "found" ? <BadgeCheck className="h-3.5 w-3.5" /> : <AlertTriangle className="h-3.5 w-3.5" />;
  return (
    <span
      className={`inline-flex h-fit items-center gap-1 rounded-[8px] px-2.5 py-1 text-xs font-semibold ${
        state === "found"
          ? "bg-teal/12 text-teal"
          : state === "review"
            ? "bg-gold/18 text-[#7a6221]"
            : "bg-coral/12 text-coral"
      }`}
    >
      {icon}
      {checklistLabels[state]}
    </span>
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

async function postFormResponse(path: string, body: FormData): Promise<AudioJobResponse> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: AUTH_HEADERS,
    body,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json() as Promise<AudioJobResponse>;
}

async function postReviewFormResponse(path: string, body: FormData): Promise<PipelineReviewResponse> {
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

async function getAudioJob(jobId: string): Promise<AudioJobResponse> {
  const response = await fetch(`${API_BASE}/sessions/audio/jobs/${jobId}`, {
    headers: AUTH_HEADERS,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json() as Promise<AudioJobResponse>;
}

async function waitForAudioJob(initialJob: AudioJobResponse): Promise<AudioJobResponse> {
  if (initialJob.status === "done" || initialJob.status === "error") return initialJob;
  let current = initialJob;
  for (let attempt = 0; attempt < 12; attempt += 1) {
    await delay(900);
    current = await getAudioJob(initialJob.job_id);
    if (current.status === "done" || current.status === "error") return current;
  }
  return current;
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function withTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  let timeoutId: number | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timeoutId = window.setTimeout(() => reject(new Error(message)), timeoutMs);
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    if (timeoutId !== undefined) window.clearTimeout(timeoutId);
  }
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

function formatTranscript(utterances: TranscriptUtterance[]) {
  return utterances.map((utterance) => `${utterance.speaker_id}: ${utterance.text}`).join("\n");
}

function splitRoleTaggedTranscript(text: string) {
  const outputLines: string[] = [];
  let changed = false;

  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;
    const parsed = transcriptLinePattern.exec(line);
    if (!parsed) {
      outputLines.push(line);
      continue;
    }

    const segments = splitRoleTaggedText(parsed[2]);
    if (!segments.length) {
      outputLines.push(line);
      continue;
    }

    changed = true;
    outputLines.push(...segments.map((segment) => `${segment.speaker_id}: ${segment.text}`));
  }

  return changed ? outputLines.join("\n") : text;
}

function splitRoleTaggedText(text: string): TranscriptUtterance[] {
  const markerPattern = /\b(doktor|hekim|hasta|asistan)\s*:\s*/gi;
  const matches = Array.from(text.matchAll(markerPattern));
  if (!matches.length) return [];

  const segments: TranscriptUtterance[] = [];
  matches.forEach((match, index) => {
    const roleLabel = (match[1] ?? "").toLocaleLowerCase("tr-TR");
    const start = match.index + match[0].length;
    const end = index + 1 < matches.length ? matches[index + 1].index : text.length;
    const segmentText = text.slice(start, end).trim();
    if (!segmentText) return;
    segments.push({
      speaker_id: speakerIdForRoleLabel(roleLabel),
      text: segmentText,
    });
  });
  return segments;
}

function speakerIdForRoleLabel(roleLabel: string) {
  if (roleLabel === "hasta") return "B";
  if (roleLabel === "asistan") return "C";
  return "A";
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

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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

function formatDuration(totalSeconds: number) {
  if (!totalSeconds) return "0:00";
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function statusText(status?: string) {
  if (!status) return "Hazır";
  if (status === "needs_dentist_role_review") return "Rol onayı";
  if (status === "awaiting_dentist_review") return "Hekim review";
  return status;
}

function procedureLabel(family: string) {
  if (family === "kanal_tedavisi") return "Kanal";
  if (family === "gecici_restorasyon") return "Geçici";
  if (family === "kompozit_dolgu") return "Kompozit";
  return family.replaceAll("_", " ");
}

function procedureStatusLabel(status: string) {
  if (status === "performed") return "Yapıldı";
  if (status === "planned") return "Planlandı";
  if (status === "discussed") return "Görüşüldü";
  if (status === "unclear") return "Belirsiz";
  return status;
}

function buildPerioDraftFromTranscript(utterances: TranscriptUtterance[]): PerioDraft {
  const teeth = new Map<number, PerioToothDraft>();
  const reviewItems: string[] = [];
  let currentTooth: number | null = null;

  for (const utterance of utterances) {
    const text = utterance.text;
    const normalized = normalizeTurkish(text);
    const tooth = extractToothNumber(normalized);
    if (tooth !== null) currentTooth = tooth;
    if (currentTooth === null) {
      reviewItems.push(`Diş numarası net değil: "${text}"`);
      continue;
    }

    const draft = getOrCreatePerioTooth(teeth, currentTooth);
    draft.source_quotes.push(text);
    const updates = extractPerioSiteUpdates(normalized, text);
    if (!updates.length) {
      reviewItems.push(`${currentTooth} için bölge/değer net değil: "${text}"`);
      draft.review = true;
      continue;
    }

    for (const update of updates) {
      draft.sites[update.site] = {
        ...draft.sites[update.site],
        ...update.value,
        source: text,
        review: update.value.pocket !== undefined && (update.value.pocket < 1 || update.value.pocket > 9),
      };
      if (draft.sites[update.site].review) {
        reviewItems.push(`${currentTooth} ${update.site} cep değeri olağan dışı görünüyor.`);
        draft.review = true;
      }
    }
  }

  const toothDrafts = Array.from(teeth.values());
  toothDrafts.forEach((tooth) => {
    const missing = perioSites.filter((site) => tooth.sites[site].pocket === undefined);
    if (missing.length) {
      tooth.review = true;
      reviewItems.push(`${tooth.tooth}: eksik bölgeler ${missing.join(", ")}`);
    }
  });

  return {
    teeth: toothDrafts.sort((left, right) => left.tooth - right.tooth),
    review_items: Array.from(new Set(reviewItems)),
    source_utterances: utterances.length,
  };
}

function getOrCreatePerioTooth(teeth: Map<number, PerioToothDraft>, tooth: number) {
  const existing = teeth.get(tooth);
  if (existing) return existing;
  const created: PerioToothDraft = {
    tooth,
    sites: emptyPerioSites(),
    source_quotes: [],
    review: false,
  };
  teeth.set(tooth, created);
  return created;
}

function emptyPerioSites(): Record<PerioSite, PerioSiteDraft> {
  return {
    MB: {},
    B: {},
    DB: {},
    ML: {},
    L: {},
    DL: {},
  };
}

function extractPerioSiteUpdates(normalized: string, source: string) {
  const updates: Array<{ site: PerioSite; value: PerioSiteDraft }> = [];
  const sitePatterns: Array<{ site: PerioSite; pattern: RegExp }> = [
    { site: "MB", pattern: /\b(mb|mesiobukkal|meziobukkal|mesio bukkal|mezio bukkal)\b/g },
    { site: "DB", pattern: /\b(db|distobukkal|disto bukkal)\b/g },
    { site: "ML", pattern: /\b(ml|mesiolingual|meziolingual|mesio lingual|mezio lingual|mesiopalatinal|meziopalatinal)\b/g },
    { site: "DL", pattern: /\b(dl|distolingual|disto lingual|distopalatinal)\b/g },
    { site: "B", pattern: /\b(bukkal|bukal)\b/g },
    { site: "L", pattern: /\b(lingual|palatinal)\b/g },
  ];

  for (const { site, pattern } of sitePatterns) {
    let match = pattern.exec(normalized);
    while (match) {
      const windowText = normalized.slice(match.index ?? 0, (match.index ?? 0) + 80);
      const pocket = extractFirstNumber(windowText);
      const value: PerioSiteDraft = {};
      if (pocket !== null) value.pocket = pocket;
      if (/\b(kanama|bop)\b/.test(windowText)) value.bleeding = !/\b(yok|negatif|hayir|hayır)\b/.test(windowText);
      if (/\b(plak|plaque)\b/.test(windowText)) value.plaque = !/\b(yok|negatif|hayir|hayır)\b/.test(windowText);
      if (/\b(furkasyon|furkasyon)\b/.test(windowText)) value.furcation = extractFurcation(windowText);
      if (Object.keys(value).length) updates.push({ site, value });
      match = pattern.exec(normalized);
    }
  }

  if (!updates.length && /\b(kanama|plak|furkasyon|cep)\b/.test(normalized)) {
    const pocket = extractFirstNumber(normalized);
    if (pocket !== null) {
      updates.push({ site: "B", value: { pocket, source, review: true } });
    }
  }
  return updates;
}

function extractToothNumber(text: string) {
  const numeric = /\b([1-4][1-8])\b/.exec(text);
  if (numeric) return Number(numeric[1]);
  const words: Array<[RegExp, number]> = [
    [/\bon bir\b/, 11],
    [/\bon iki\b/, 12],
    [/\bon uc\b/, 13],
    [/\bon dort\b/, 14],
    [/\bkirk bes\b/, 45],
    [/\bkirk alti\b/, 46],
    [/\bkirk yedi\b/, 47],
    [/\bkirk sekiz\b/, 48],
    [/\botuz alti\b/, 36],
    [/\botuz yedi\b/, 37],
    [/\botuz sekiz\b/, 38],
    [/\byirmi alti\b/, 26],
    [/\byirmi yedi\b/, 27],
    [/\byirmi sekiz\b/, 28],
  ];
  return words.find(([pattern]) => pattern.test(text))?.[1] ?? null;
}

function extractFirstNumber(text: string) {
  const numeric = /\b([1-9]|1[0-2])\b/.exec(text);
  if (numeric) return Number(numeric[1]);
  const words: Array<[RegExp, number]> = [
    [/\bbir\b/, 1],
    [/\biki\b/, 2],
    [/\buc\b/, 3],
    [/\bdort\b/, 4],
    [/\bbes\b/, 5],
    [/\balti\b/, 6],
    [/\byedi\b/, 7],
    [/\bsekiz\b/, 8],
    [/\bdokuz\b/, 9],
  ];
  return words.find(([pattern]) => pattern.test(text))?.[1] ?? null;
}

function extractFurcation(text: string) {
  const match = /\b(f[123]|[123])\b/.exec(text);
  return match ? match[1].toUpperCase() : "var";
}

function normalizeTurkish(text: string) {
  return text
    .toLocaleLowerCase("tr-TR")
    .replaceAll("ı", "i")
    .replaceAll("ğ", "g")
    .replaceAll("ü", "u")
    .replaceAll("ş", "s")
    .replaceAll("ö", "o")
    .replaceAll("ç", "c");
}

function PerioDraftPanel({ draft, isLoading }: { draft: PerioDraft | null; isLoading: boolean }) {
  if (isLoading) {
    return (
      <section className="rounded-[8px] border border-black/10 bg-paper p-4">
        <h3 className="text-lg font-semibold">Perio chart hazırlanıyor</h3>
        <p className="mt-2 text-sm font-semibold leading-6 text-muted">Dikte transkripte çevriliyor ve bölgeler yapılandırılıyor.</p>
      </section>
    );
  }

  if (!draft) {
    return (
      <section className="rounded-[8px] border border-black/10 bg-paper p-4">
        <h3 className="text-lg font-semibold">Periodontal çizelge taslağı</h3>
        <p className="mt-2 text-sm font-semibold leading-6 text-muted">
          Perio dikte modunda kayıt alın. Örnek: "46 mesiobukkal 4 kanama var, bukkal 3 plak yok, distobukkal 5".
        </p>
      </section>
    );
  }

  return (
    <div className="grid gap-4">
      {draft.review_items.length ? (
        <section className="rounded-[8px] border border-gold/30 bg-gold/10 p-4">
          <div className="flex items-center gap-2 text-[#7a6221]">
            <AlertTriangle className="h-5 w-5" aria-hidden="true" />
            <h3 className="text-lg font-semibold">İnceleme gerekenler</h3>
          </div>
          <div className="mt-3 grid gap-2 text-sm font-semibold leading-6 text-[#7a6221]">
            {draft.review_items.slice(0, 6).map((item) => (
              <p key={item}>{item}</p>
            ))}
          </div>
        </section>
      ) : null}

      <section className="rounded-[8px] border border-black/10 bg-paper p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">Perio chart</p>
            <h3 className="mt-1 text-lg font-semibold">Altı bölgeli periodontal taslak</h3>
          </div>
          <StatusBadge label="Taslak" tone={draft.review_items.length ? "warning" : "success"} />
        </div>
        <div className="mt-4 grid gap-3">
          {draft.teeth.map((tooth) => (
            <div key={tooth.tooth} className="rounded-[8px] border border-black/10 bg-white p-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-lg font-semibold">{tooth.tooth}</p>
                <StatusDot status={tooth.review ? "review_needed" : "clear"} />
              </div>
              <div className="mt-3 grid grid-cols-6 gap-2">
                {perioSites.map((site) => {
                  const value = tooth.sites[site];
                  return (
                    <div key={`${tooth.tooth}-${site}`} className="min-h-[88px] rounded-[8px] border border-black/10 bg-linen p-2 text-center">
                      <p className="text-xs font-semibold text-muted">{site}</p>
                      <p className={`mt-1 text-2xl font-semibold ${value.pocket !== undefined ? "text-ink" : "text-muted/45"}`}>
                        {value.pocket ?? "-"}
                      </p>
                      <div className="mt-1 flex justify-center gap-1 text-[10px] font-semibold">
                        {value.bleeding ? <span className="rounded bg-coral/12 px-1 text-coral">BOP</span> : null}
                        {value.plaque ? <span className="rounded bg-gold/18 px-1 text-[#7a6221]">PL</span> : null}
                        {value.furcation ? <span className="rounded bg-teal/12 px-1 text-teal">F {value.furcation}</span> : null}
                      </div>
                    </div>
                  );
                })}
              </div>
              {tooth.source_quotes[0] ? (
                <p className="mt-3 text-xs font-semibold leading-5 text-muted">{tooth.source_quotes[0]}</p>
              ) : null}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function DentalChart({ procedures, approved }: { procedures: ProcedureObject[]; approved: boolean }) {
  const chartAdapter = proceduresToDentalChartAdapter(procedures);
  const firstProcedure = procedures.find((procedure) => procedure.tooth_number_fdi) ?? null;
  return (
    <div className="mt-4 rounded-[8px] bg-linen p-4">
      <div className="rounded-[8px] bg-white p-3 shadow-line">
        <Odontogram
          teethConditions={chartAdapter.teethConditions}
          readOnly
          notation="FDI"
          showLabels
          showTooltip
          layout="square"
          styles={{ maxWidth: "100%" }}
        />
      </div>
      {chartAdapter.surfaceConditions.length ? (
        <div className="mt-3 grid gap-2">
          {chartAdapter.surfaceConditions.map((item) => (
            <div key={`${item.tooth}-${item.surfaces.join("")}-${item.condition}`} className="rounded-[8px] bg-white p-3 text-sm font-semibold shadow-line">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-[8px] bg-linen px-2 py-1 text-xs text-muted">FDI {item.tooth}</span>
                {item.surfaces.map((surface) => (
                  <span key={`${item.tooth}-${surface}`} className="rounded-[8px] px-2 py-1 text-xs text-white" style={{ backgroundColor: item.color }}>
                    {surface}
                  </span>
                ))}
                <span className="text-muted">{dentalConditionLabel(item.condition)} · {procedureStatusLabel(item.status)}</span>
              </div>
            </div>
          ))}
        </div>
      ) : null}
      <div className="mt-4 grid grid-cols-3 gap-2 text-sm">
        <ChartMetric label="FDI" value={firstProcedure?.tooth_number_fdi ? `${firstProcedure.tooth_number_fdi}` : "Belirsiz"} />
        <ChartMetric label="Durum" value={firstProcedure ? procedureStatusLabel(firstProcedure.status) : "Bekliyor"} />
        <ChartMetric label="Mod" value={approved ? "Onaylı" : "Read-only"} />
      </div>
    </div>
  );
}

function proceduresToDentalChartAdapter(procedures: ProcedureObject[]): DentalChartAdapterResult {
  const grouped = new Map<string, { labelKey: string; status: string; teeth: Set<string> }>();
  const surfaceConditions: DentalSurfaceCondition[] = [];
  for (const procedure of procedures) {
    if (!procedure.tooth_number_fdi) continue;
    const labelKey = dentalChartConditionKey(procedure);
    const colorKey = procedureConditionColors[labelKey] ? labelKey : "other";
    const status = procedure.status || "unclear";
    const key = `${colorKey}:${status}`;
    const group = grouped.get(key) ?? { labelKey: colorKey, status, teeth: new Set<string>() };
    group.teeth.add(`teeth-${procedure.tooth_number_fdi}`);
    grouped.set(key, group);
    const surfaces = normalizeProcedureSurfaces(procedure);
    if (surfaces.length) {
      surfaceConditions.push({
        tooth: procedure.tooth_number_fdi,
        surfaces,
        condition: procedure.condition || labelKey,
        color: procedureConditionColors[colorKey] ?? procedureConditionColors.other,
        status,
      });
    }
  }

  const teethConditions = Array.from(grouped.values()).map(({ labelKey, status, teeth }) => {
    const color = procedureConditionColors[labelKey] ?? procedureConditionColors.other;
    return {
      label: `${dentalConditionLabel(labelKey)} · ${procedureStatusLabel(status)}`,
      teeth: Array.from(teeth),
      fillColor: color,
      outlineColor: color,
    };
  });

  return { teethConditions, surfaceConditions };
}

function dentalChartConditionKey(procedure: ProcedureObject) {
  if (procedure.condition && procedure.condition !== "unclear") return procedure.condition;
  if (procedure.procedure_family === "kanal_tedavisi") return "rct";
  if (procedure.procedure_family === "kompozit_dolgu") return "composite";
  if (procedure.procedure_family === "dis_cekimi") return "missing";
  return procedure.procedure_family || "other";
}

function normalizeProcedureSurfaces(procedure: ProcedureObject): ToothSurface[] {
  const raw = procedure.surfaces ?? procedure.surface;
  const values = Array.isArray(raw) ? raw : raw ? [raw] : [];
  return values.filter(isToothSurface);
}

function isToothSurface(value: unknown): value is ToothSurface {
  return value === "O" || value === "M" || value === "D" || value === "V" || value === "L";
}

function dentalConditionLabel(value: string) {
  if (value === "caries") return "Çürük";
  if (value === "composite") return "Kompozit";
  if (value === "amalgam") return "Amalgam";
  if (value === "inlay") return "Inlay";
  if (value === "onlay") return "Onlay";
  if (value === "crown") return "Kron";
  if (value === "bridge") return "Köprü";
  if (value === "prosthesis") return "Protez";
  if (value === "implant") return "İmplant";
  if (value === "rct") return "Kanal";
  if (value === "missing") return "Eksik";
  return procedureLabel(value);
}

function ChartMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[8px] bg-white p-3 shadow-line">
      <p className="font-semibold">{label}</p>
      <p className="mt-1 text-muted">{value}</p>
    </div>
  );
}
