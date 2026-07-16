"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Save, X } from "lucide-react";
import { useHeader } from "@/components/app/HeaderContext";
import { ApprovedExport } from "@/components/review/ApprovedExport";
import { CodeSuggestionsPanel } from "@/components/review/CodeSuggestionsPanel";
import { DentalChartPanel } from "@/components/review/DentalChartPanel";
import { NoteDocument } from "@/components/review/NoteDocument";
import { PatientRecordPanel, type MedicalHistory, type PatientInformation } from "@/components/review/PatientRecordPanel";
import { PerioChartPanel, type PerioSessionResult } from "@/components/review/PerioChartPanel";
import { TranscriptDrawer } from "@/components/review/TranscriptDrawer";
import { TranscriptInput } from "@/components/review/TranscriptInput";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DraftBadge } from "@/components/ui/draft-badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { fetchPatientSessions } from "@/lib/patients-api";
import { parsePatientRecordEditCommand } from "@/lib/patient-record-edit";

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
  source_speaker?: string | null;
  source_role_confidence?: "clear" | "uncertain";
};

type ClinicalNote = {
  patient_information: PatientInformation;
  medical_history: MedicalHistory;
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
  export_payload?: ExportPayload | null;
};

type SessionMetadata = {
  patient_id?: string | null;
  session_type?: "clinical_note" | "perio";
  status?: string;
  started_at?: string | null;
};

type PerioExportPayload = {
  session_id: string;
  perio_text: string;
  audit: {
    action: string;
    reviewer_user_id?: string | null;
    approved: boolean;
    created_at_utc: string;
    source: string;
  };
  warning: string;
};

type PerioApprovalResponse = {
  session_id: string;
  status: "approved";
  review_state: "approved";
  export_payload: PerioExportPayload;
};

type SessionReviewSnapshot = {
  snapshot_version: number;
  session_id: string;
  session_type: "clinical_note" | "perio";
  transcript: TranscriptUtterance[];
  clinical_review?: PipelineReviewResponse | null;
  perio_result?: PerioSessionResult | null;
  perio_approval?: PerioApprovalResponse | null;
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

const transcriptLinePattern = /^([A-Za-zÇĞİÖŞÜçğıöşü0-9_-]+)\s*:\s*(.+)$/;

export default function ReviewPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const { clearHeader, setHeader } = useHeader();
  const [sessionId] = useState(params.id);
  const [patientName, setPatientName] = useState("Yeni Görüşme");
  const [patientId, setPatientId] = useState<string | null>(null);
  const [encounterAt, setEncounterAt] = useState(() => toDatetimeLocalValue(new Date()));
  const [transcriptText, setTranscriptText] = useState("");
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [selectedCode, setSelectedCode] = useState("");
  const [approved, setApproved] = useState(false);
  const [response, setResponse] = useState<PipelineReviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportPayload, setExportPayload] = useState<ExportPayload | null>(null);
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const [editableNote, setEditableNote] = useState<ClinicalNote | null>(null);
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState("transcript");
  const [activeReviewArea, setActiveReviewArea] = useState<"clinical" | "patient">("clinical");
  const [sessionType, setSessionType] = useState<"clinical_note" | "perio">("clinical_note");
  const [persistedPerioResult, setPersistedPerioResult] = useState<PerioSessionResult | null>(null);
  const [perioExportPayload, setPerioExportPayload] = useState<PerioExportPayload | null>(null);
  const [perioPatientInformation, setPerioPatientInformation] = useState<PatientInformation>({});
  const [perioMedicalHistory, setPerioMedicalHistory] = useState<MedicalHistory>({});
  const [reviewEditCommand, setReviewEditCommand] = useState("");
  const [reviewEditMessage, setReviewEditMessage] = useState<string | null>(null);

  const utterances = useMemo(() => parseTranscript(transcriptText), [transcriptText]);
  const transcriptDiagnostics = useMemo(() => inspectTranscript(transcriptText), [transcriptText]);
  const canAnalyzeTranscript = transcriptDiagnostics.utteranceCount > 0 && transcriptDiagnostics.invalidLines.length === 0;

  const dentistReview = response?.dentist_review ?? null;
  const displayedNote = editableNote ?? dentistReview?.note ?? null;
  const procedures = dentistReview?.procedures ?? [];
  const noteSections = displayedNote ? noteSectionsFromBackend(displayedNote) : [];
  const needsRoleReview = Boolean(response?.role_review_required);
  const hasAnalysisDraft = Boolean(displayedNote) && (response?.next_action === "review_note_and_codes" || response?.role_review_required);

  useEffect(() => {
    let active = true;
    Promise.all([
      fetch(`${API_BASE}/sessions/${sessionId}/review`, { headers: AUTH_HEADERS }),
      fetch(`${API_BASE}/sessions/${sessionId}`, { headers: AUTH_HEADERS }),
    ])
      .then(async ([reviewResponse, metadataResponse]) => {
        const snapshot = reviewResponse.ok ? ((await reviewResponse.json()) as SessionReviewSnapshot) : null;
        const metadata = metadataResponse.ok ? ((await metadataResponse.json()) as SessionMetadata) : null;
        const patient = metadata?.patient_id ? await fetchPatientSessions(metadata.patient_id).catch(() => null) : null;
        return { snapshot, metadata, patient };
      })
      .then(({ snapshot, metadata, patient }) => {
        if (!active) return;
        const nextSessionType = snapshot?.session_type ?? metadata?.session_type ?? "clinical_note";
        setSessionType(nextSessionType);
        setPatientId(metadata?.patient_id ?? null);
        setPatientName(patient ? displayPatientHeader(patient.initials, patient.external_id) : "Yeni Görüşme");
        if (patient && nextSessionType === "perio") {
          const displayName = patient.display_name ?? patient.initials;
          setPerioPatientInformation(displayName ? { display_name: patientRecordTextField(displayName) } : {});
        }
        if (metadata?.started_at) setEncounterAt(toDatetimeLocalValue(new Date(metadata.started_at)));
        if (!snapshot) return;

        const snapshotUtterances = snapshot.transcript ?? [];
        setTranscriptText(snapshotUtterances.map((item) => `${item.speaker_id}: ${item.text}`).join("\n"));
        setPersistedPerioResult(snapshot.perio_result ?? null);
        setPerioExportPayload(snapshot.perio_approval?.export_payload ?? null);
        if (nextSessionType === "perio") {
          setApproved(metadata?.status === "approved" && Boolean(snapshot.perio_approval?.export_payload));
        }

        const clinicalReview = snapshot.clinical_review;
        if (!clinicalReview) return;
        setResponse(clinicalReview);
        setEditableNote(clinicalReview.dentist_review?.note ?? null);
        setExportPayload(clinicalReview.export_payload ?? null);
        setApproved(clinicalReview.status === "approved" && Boolean(clinicalReview.export_payload));
        if (clinicalReview.role_review) {
          setSpeakers(
            clinicalReview.role_review.speakers.map((speaker) => ({
              id: speaker.speaker_id,
              role: speaker.role,
              status: speaker.status,
              utterances: speaker.utterance_count,
              sample: sampleForSpeaker(speaker.speaker_id, snapshotUtterances),
              reason: speaker.reason ?? undefined,
            })),
          );
        }
        const firstCode = clinicalReview.dentist_review?.procedures[0]?.candidates[0]?.code;
        if (firstCode) setSelectedCode(firstCode);
      })
      .catch((reason) => {
        if (active) setError(errorMessage(reason));
      });
    return () => {
      active = false;
    };
  }, [sessionId]);

  useEffect(() => {
    const hasPerioDraft = sessionType === "perio" && Boolean(persistedPerioResult);
    if ((!hasAnalysisDraft && !hasPerioDraft) || approved) {
      clearHeader();
      return;
    }

    setHeader({
      title: patientName.trim() || "Yeni Görüşme",
      subtitle: formatEncounterDate(encounterAt),
      badge: <DraftBadge />,
      actions: (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            className="h-10 rounded-lg px-4 text-muted-foreground hover:bg-muted"
            onClick={() => {
              if (sessionType === "perio") {
                router.push(patientId ? `/patients/${encodeURIComponent(patientId)}` : "/");
                return;
              }
              setResponse(null);
              setEditableNote(null);
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
            onClick={() => void (sessionType === "perio" ? approvePerioReview() : approveClinicalReview())}
            disabled={isLoading || (sessionType === "perio" ? !persistedPerioResult : !displayedNote)}
          >
            {isLoading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <Save className="mr-2 size-4" />}
            Onayla ve Kaydet
          </Button>
        </div>
      ),
    });

    return () => clearHeader();
  }, [approved, clearHeader, displayedNote, encounterAt, hasAnalysisDraft, isLoading, patientId, patientName, persistedPerioResult, router, sessionType, setHeader]);

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

  async function approvePerioReview() {
    if (!persistedPerioResult) {
      setError("Onay için önce periodontal taslak oluşturulmalı.");
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const result = await postPerioApproval(`/sessions/${encodeURIComponent(sessionId)}/perio/approve`);
      setApproved(true);
      setPerioExportPayload(result.export_payload);
      setExportMessage("Hekim onayı kaydedildi; periodontal çıktı kopyalama ve indirme için hazır.");
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

  function updatePatientField(field: keyof PatientInformation, value: string) {
    if (isPerioSession) {
      setPerioPatientInformation((current) => ({ ...current, [field]: value.trim() ? manualTextField(value) : null }));
      return;
    }
    setEditableNote((current) => current ? ({ ...current, patient_information: { ...current.patient_information, [field]: value.trim() ? manualTextField(value) : null } }) : current);
  }

  function updateMedicalHistory(field: keyof MedicalHistory, value: boolean | null, detail: string) {
    if (isPerioSession) {
      setPerioMedicalHistory((current) => ({ ...current, [field]: value === null && !detail.trim() ? null : manualMedicalField(value, detail) }));
      return;
    }
    setEditableNote((current) => current ? ({ ...current, medical_history: { ...current.medical_history, [field]: value === null && !detail.trim() ? null : manualMedicalField(value, detail) } }) : current);
  }

  function applyReviewEditCommand() {
    const correction = parsePatientRecordEditCommand(reviewEditCommand.trim());
    if (!correction) {
      setReviewEditMessage("Bu komut güvenle bir hasta kaydı alanına eşleştirilemedi. Alanı Hasta Kaydı ekranından düzenleyin.");
      return;
    }
    updatePatientField(correction.field, correction.value);
    setReviewEditCommand("");
    setReviewEditMessage(`${correction.label} hasta kaydında güncellendi.`);
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

  async function copyPerioExportToClipboard() {
    if (!perioExportPayload) return;
    await navigator.clipboard.writeText(perioExportPayload.perio_text);
    setExportMessage("Perio export metni panoya kopyalandı.");
  }

  function downloadPerioExportTxt() {
    if (!perioExportPayload) return;
    const blob = new Blob([perioExportPayload.perio_text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${perioExportPayload.session_id}-tandela-perio-export.txt`;
    link.click();
    URL.revokeObjectURL(url);
    setExportMessage("Perio TXT dosyası indirildi.");
  }

  const hasDentalChart = procedures.some((procedure) => procedure.procedure.tooth_number_fdi);
  const hasCodeSuggestions = procedures.some((procedure) => procedure.candidates.length);
  const isPerioSession = sessionType === "perio";
  const patientInformation = isPerioSession ? perioPatientInformation : displayedNote?.patient_information ?? {};
  const medicalHistory = isPerioSession ? perioMedicalHistory : displayedNote?.medical_history ?? {};
  const defaultTab = isPerioSession ? "perio" : hasAnalysisDraft && displayedNote ? "note" : hasDentalChart ? "chart" : hasCodeSuggestions ? "codes" : "transcript";
  useEffect(() => {
    setActiveWorkspaceTab(defaultTab);
  }, [defaultTab]);

  if (approved && sessionType === "perio" && perioExportPayload) {
    return (
      <ApprovedExport
        message={exportMessage}
        onCopy={() => void copyPerioExportToClipboard()}
        onDownloadTxt={downloadPerioExportTxt}
      />
    );
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

  if (hasAnalysisDraft && displayedNote) {
    return (
      <main className="bg-background p-4 md:p-6">
        <div className="mx-auto max-w-7xl space-y-5">
          {needsRoleReview ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="font-semibold">Konuşmacı rolleri kesin değil — kontrol edin</p>
                <Badge className="rounded-full bg-amber-100 text-amber-900 hover:bg-amber-100">
                  {response?.uncertain_speakers?.length ?? speakers.filter((speaker) => speaker.status !== "clear").length} konuşmacı belirsiz
                </Badge>
              </div>
            </div>
          ) : null}

          <Tabs value={activeReviewArea} onValueChange={(value) => setActiveReviewArea(value as "clinical" | "patient")} className="gap-5">
            <TabsList className="grid h-auto w-full max-w-xl grid-cols-2 rounded-xl bg-muted p-1.5">
              <TabsTrigger value="clinical" className="h-11 rounded-lg px-5 text-base font-semibold">Klinik Değerlendirme</TabsTrigger>
              <TabsTrigger value="patient" className="h-11 rounded-lg px-5 text-base font-semibold">Hasta Kaydı</TabsTrigger>
            </TabsList>

            <TabsContent value="clinical">
          <Tabs value={activeWorkspaceTab} onValueChange={setActiveWorkspaceTab} className="gap-4">
            <TabsList className="w-full justify-start overflow-x-auto">
              <TabsTrigger value="note">Klinik Not</TabsTrigger>
              {hasDentalChart ? <TabsTrigger value="chart">Diş Şeması</TabsTrigger> : null}
              {hasCodeSuggestions ? <TabsTrigger value="codes">Kod Önerileri</TabsTrigger> : null}
              {transcriptText.trim() ? <TabsTrigger value="transcript">Transkript</TabsTrigger> : null}
              {isPerioSession ? <TabsTrigger value="perio">Perio</TabsTrigger> : null}
            </TabsList>

            <TabsContent value="note">
              <NoteDocument
                sections={noteSections}
                uncertainItems={dentistReview?.uncertain_items ?? []}
                onSentenceChange={updateNoteSentence}
                onSourceRoleChange={(speakerId, role) => void patchSpeakerRole(speakerId, role)}
              />
              <Card className="mt-4 border-border bg-card shadow-card">
                <CardHeader>
                  <CardTitle className="text-base">Notu Düzenle</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Textarea
                    value={reviewEditCommand}
                    onChange={(event) => setReviewEditCommand(event.target.value)}
                    placeholder="Örn: Mesleği mühendis, öğretmen değil."
                    aria-label="Review düzeltme komutu"
                  />
                  <div className="flex flex-wrap items-center gap-3">
                    <Button type="button" onClick={applyReviewEditCommand} disabled={!reviewEditCommand.trim()}>Uygula</Button>
                    {reviewEditMessage ? <p className="text-sm text-muted-foreground">{reviewEditMessage}</p> : null}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
            {hasDentalChart ? (
              <TabsContent value="chart">
                <DentalChartPanel procedures={procedures.map((procedure) => procedure.procedure)} approved={approved} />
              </TabsContent>
            ) : null}
            {hasCodeSuggestions ? (
              <TabsContent value="codes">
                <CodeSuggestionsPanel
                  procedures={procedures}
                  selectedCode={selectedCode}
                  onSelectedCodeChange={setSelectedCode}
                />
              </TabsContent>
            ) : null}
            {transcriptText.trim() ? (
              <TabsContent value="transcript">
                <TranscriptTab transcriptText={transcriptText} onTranscriptChange={setTranscriptText} />
              </TabsContent>
            ) : null}
            {isPerioSession ? (
              <TabsContent value="perio">
                <PerioChartPanel
                  sessionId={sessionId}
                  apiBase={API_BASE}
                  authHeaders={AUTH_HEADERS}
                  initialResult={persistedPerioResult}
                />
              </TabsContent>
            ) : null}
          </Tabs>
            </TabsContent>
            <TabsContent value="patient">
              <PatientRecordPanel
                patientInformation={patientInformation}
                medicalHistory={medicalHistory}
                onPatientFieldChange={updatePatientField}
                onMedicalHistoryChange={updateMedicalHistory}
              />
            </TabsContent>
          </Tabs>

            {error ? (
            <p className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm font-medium text-destructive">
                {error}
              </p>
            ) : null}
        </div>
      </main>
    );
  }

  if (isPerioSession) {
    return (
      <main className="min-h-[calc(100vh-4rem)] bg-background p-4 md:p-6">
        <div className="mx-auto max-w-7xl space-y-5">
          <Tabs value={activeReviewArea} onValueChange={(value) => setActiveReviewArea(value as "clinical" | "patient")} className="gap-5">
            <TabsList className="grid h-auto w-full max-w-xl grid-cols-2 rounded-xl bg-muted p-1.5">
              <TabsTrigger value="clinical" className="h-11 rounded-lg px-5 text-base font-semibold">Klinik Değerlendirme</TabsTrigger>
              <TabsTrigger value="patient" className="h-11 rounded-lg px-5 text-base font-semibold">Hasta Kaydı</TabsTrigger>
            </TabsList>
            <TabsContent value="clinical">
              <PerioChartPanel
                sessionId={sessionId}
                apiBase={API_BASE}
                authHeaders={AUTH_HEADERS}
                initialResult={persistedPerioResult}
              />
            </TabsContent>
            <TabsContent value="patient">
              <PatientRecordPanel
                patientInformation={patientInformation}
                medicalHistory={medicalHistory}
                onPatientFieldChange={updatePatientField}
                onMedicalHistoryChange={updateMedicalHistory}
              />
            </TabsContent>
          </Tabs>
        </div>
      </main>
    );
  }

  return (
    <main className="bg-background p-4 md:p-6">
      <div className="mx-auto max-w-5xl">
        <Tabs value={activeWorkspaceTab} onValueChange={setActiveWorkspaceTab} className="gap-4">
          <TabsList>
            <TabsTrigger value="transcript">Transkript</TabsTrigger>
          </TabsList>
          <TabsContent value="transcript">
            <Card>
              <CardHeader>
                <CardTitle>Transkript</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <TranscriptTab transcriptText={transcriptText} onTranscriptChange={setTranscriptText} />
                <Button type="button" onClick={() => void analyzeTranscript()} disabled={isLoading || !canAnalyzeTranscript}>
                  Analiz Et
                </Button>
                {error ? <p className="text-sm font-medium text-destructive">{error}</p> : null}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
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

async function postPerioApproval(path: string): Promise<PerioApprovalResponse> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: AUTH_HEADERS,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json() as Promise<PerioApprovalResponse>;
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

function TranscriptTab({
  transcriptText,
  onTranscriptChange,
}: {
  transcriptText: string;
  onTranscriptChange: (value: string) => void;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <Textarea
          className="min-h-[520px] resize-y bg-background text-sm leading-6"
          value={transcriptText}
          onChange={(event) => onTranscriptChange(event.target.value)}
          aria-label="Transkript"
        />
      </CardContent>
    </Card>
  );
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
    source_speaker: sentence.source_speaker,
    source_role_confidence: sentence.source_role_confidence,
  };
}

function manualTextField(value: string) {
  return { value, source_quote: "Hekim tarafından manuel eklendi", source_role: "dentist" as const, source_speaker: "manual", is_uncertain: false };
}

function patientRecordTextField(value: string) {
  return {
    value,
    source_quote: "Mevcut hasta kaydı",
    source_role: "unknown" as const,
    source_speaker: "record",
    is_uncertain: false,
  };
}

function manualMedicalField(value: boolean | null, detail: string) {
  return { value, detail: detail.trim() || null, source_quote: "Hekim tarafından manuel eklendi", source_role: "dentist" as const, source_speaker: "manual", is_uncertain: false };
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

function displayPatientHeader(initials: string | null, externalId: string | null) {
  const name = initials?.trim() || "İsimsiz hasta";
  return externalId?.trim() ? `${name} · ${externalId.trim()}` : name;
}
