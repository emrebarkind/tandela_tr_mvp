"use client";

import { useRef, useState } from "react";
import { Mic, MicOff, Square } from "lucide-react";
import { Button } from "@/components/ui/button";

type LiveTranscriptRecorderProps = {
  sessionId: string;
  apiBase: string;
  disabled?: boolean;
  onTranscriptLine: (line: string) => void;
  onRecordingStopped?: (audioBlob: Blob | null) => void;
};

type StreamEvent = {
  type: "ready" | "transcript" | "error";
  session_id?: string;
  speaker_id?: string;
  text?: string;
  is_final?: boolean;
  message?: string;
};

export function LiveTranscriptRecorder({
  sessionId,
  apiBase,
  disabled,
  onTranscriptLine,
  onRecordingStopped,
}: LiveTranscriptRecorderProps) {
  const [state, setState] = useState<"idle" | "connecting" | "recording" | "stopping">("idle");
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const isRecording = state === "recording" || state === "connecting";

  async function startRecording() {
    if (isRecording || disabled) return;
    setError(null);
    setInterim("");
    setState("connecting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const socket = new WebSocket(`${wsBase(apiBase)}/ws/transcribe?session_id=${encodeURIComponent(sessionId)}`);
      socketRef.current = socket;
      chunksRef.current = [];

      socket.onmessage = (event) => {
        const parsed = parseStreamEvent(event.data);
        if (!parsed) return;
        if (parsed.type === "error") {
          setError(parsed.message ?? "Canlı transkript akışı durdu.");
          return;
        }
        if (parsed.type !== "transcript" || !parsed.text?.trim()) return;
        const speaker = parsed.speaker_id?.trim() || "A";
        const line = `${speaker}: ${parsed.text.trim()}`;
        if (parsed.is_final) {
          setInterim("");
          onTranscriptLine(line);
        } else {
          setInterim(line);
        }
      };

      socket.onerror = () => setError("Canlı transkript bağlantısı kurulamadı.");
      socket.onopen = () => {
        const recorder = new MediaRecorder(stream, { mimeType: preferredMimeType() });
        mediaRecorderRef.current = recorder;
        recorder.ondataavailable = async (event) => {
          if (!event.data.size) return;
          chunksRef.current.push(event.data);
          if (socket.readyState !== WebSocket.OPEN) return;
          socket.send(await event.data.arrayBuffer());
        };
        recorder.onstop = () => {
          const blob = chunksRef.current.length ? new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" }) : null;
          chunksRef.current = [];
          window.setTimeout(() => onRecordingStopped?.(blob), 350);
        };
        recorder.start(500);
        setState("recording");
      };
    } catch (caught) {
      stopTracks();
      setState("idle");
      setError(caught instanceof Error ? caught.message : "Mikrofon başlatılamadı.");
    }
  }

  function stopRecording() {
    if (!isRecording) return;
    setState("stopping");
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "stop" }));
      window.setTimeout(() => socket.close(), 250);
    }
    stopTracks();
    setState("idle");
  }

  function stopTracks() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    mediaRecorderRef.current = null;
  }

  return (
    <>
      <div className="relative mx-auto mb-8 size-28">
        <div className={`absolute inset-0 rounded-full bg-[#31634B]/20 ${isRecording ? "animate-pulse" : ""}`} />
        <button
          className={`relative z-10 flex size-28 items-center justify-center rounded-full text-white shadow-lg transition-all hover:scale-105 active:scale-95 ${
            isRecording ? "bg-[#D4503A]" : "bg-[#31634B]"
          }`}
          type="button"
          disabled={disabled || state === "connecting" || state === "stopping"}
          onClick={() => (isRecording ? stopRecording() : void startRecording())}
          aria-label={isRecording ? "Kaydı durdur" : "Kaydı başlat"}
        >
          {isRecording ? <MicOff className="size-12" aria-hidden="true" /> : <Mic className="size-12" aria-hidden="true" />}
        </button>
      </div>

      <div>
        <h2 className="mb-2 text-xl font-semibold tracking-tight text-[#0A1F1B]">
          {isRecording ? "Görüşme Kaydediliyor..." : state === "stopping" ? "Kayıt Durduruluyor..." : "Görüşme Kaydı"}
        </h2>
        <p className="mx-auto max-w-xs text-sm leading-6 text-[#404943]">
          {isRecording
            ? "Sesiniz yapay zeka tarafından gerçek zamanlı olarak metne dönüştürülüyor."
            : "Kaydı başlatın; analiz kayıt bittikten sonra çalışır."}
        </p>
      </div>

      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <Button type="button" variant="outline" className="h-11 rounded-full border-[#717973] bg-white px-5 text-[#404943]">
          <Square className="mr-2 size-4" />
          Duraklat
        </Button>
        <Button
          type="button"
          className={`h-11 rounded-full px-6 font-semibold text-white shadow-sm ${isRecording ? "bg-[#D4503A] hover:bg-[#BE4030]" : "bg-[#31634B] hover:bg-[#4A7C63]"}`}
          disabled={disabled || state === "connecting" || state === "stopping"}
          onClick={() => (isRecording ? stopRecording() : void startRecording())}
        >
          {isRecording ? <Square className="mr-2 size-4" /> : <Mic className="mr-2 size-4" />}
          {isRecording ? "Kaydı Bitir" : "Kaydı Başlat"}
        </Button>
      </div>

      {interim ? (
        <div className="mt-5 rounded-2xl border border-[#C0C9C1] bg-[#E1F9F2] px-4 py-3 text-sm leading-6 text-[#404943]">
          {interim}
        </div>
      ) : null}
      {error ? <p className="mt-4 text-sm font-medium text-destructive">{error}</p> : null}
    </>
  );
}

function preferredMimeType() {
  if (typeof MediaRecorder === "undefined") return "";
  if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) return "audio/webm;codecs=opus";
  if (MediaRecorder.isTypeSupported("audio/webm")) return "audio/webm";
  return "";
}

function wsBase(apiBase: string) {
  if (apiBase.startsWith("https://")) return apiBase.replace("https://", "wss://");
  if (apiBase.startsWith("http://")) return apiBase.replace("http://", "ws://");
  return apiBase;
}

function parseStreamEvent(raw: unknown): StreamEvent | null {
  if (typeof raw !== "string") return null;
  try {
    return JSON.parse(raw) as StreamEvent;
  } catch {
    return null;
  }
}
