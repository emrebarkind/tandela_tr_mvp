"use client";

import { useEffect, useRef, useState } from "react";
import { Mic, MicOff, Square } from "lucide-react";
import { Button } from "@/components/ui/button";

type LiveTranscriptRecorderProps = {
  sessionId: string;
  apiBase: string;
  disabled?: boolean;
  showInlineControls?: boolean;
  controlCommand?: { action: "start" | "stop" | "pause" | "resume"; nonce: number } | null;
  onStateChange?: (state: "idle" | "connecting" | "recording" | "paused" | "stopping") => void;
  onElapsedChange?: (elapsedSec: number) => void;
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

type BrowserWindowWithAudioContext = Window & {
  webkitAudioContext?: typeof AudioContext;
};

export function LiveTranscriptRecorder({
  sessionId,
  apiBase,
  disabled,
  showInlineControls = true,
  controlCommand,
  onStateChange,
  onElapsedChange,
  onTranscriptLine,
  onRecordingStopped,
}: LiveTranscriptRecorderProps) {
  const [state, setState] = useState<"idle" | "connecting" | "recording" | "paused" | "stopping">("idle");
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [levels, setLevels] = useState<number[]>(() => Array.from({ length: 32 }, () => 0.08));
  const [elapsedSec, setElapsedSec] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const elapsedBaseRef = useRef(0);

  const isRecording = state === "recording" || state === "connecting";
  const isCaptureActive = state === "recording" || state === "connecting" || state === "paused";
  const statusText =
    state === "recording"
      ? "Dinleniyor..."
      : state === "paused"
        ? "Duraklatıldı"
        : state === "connecting" || state === "stopping" || disabled
          ? "İşleniyor..."
          : "Kayda hazır";

  useEffect(() => () => stopMeter(), []);

  useEffect(() => {
    onStateChange?.(state);
  }, [onStateChange, state]);

  useEffect(() => {
    if (!controlCommand) return;
    if (controlCommand.action === "start") void startRecording();
    if (controlCommand.action === "stop") stopRecording();
    if (controlCommand.action === "pause") pauseRecording();
    if (controlCommand.action === "resume") {
      void resumeRecording();
    }
  }, [controlCommand]);

  useEffect(() => {
    if (state !== "recording") return undefined;
    startedAtRef.current = Date.now() - elapsedBaseRef.current * 1000;
    const timer = window.setInterval(() => {
      const elapsed = Math.floor((Date.now() - (startedAtRef.current ?? Date.now())) / 1000);
      elapsedBaseRef.current = elapsed;
      setElapsedSec(elapsed);
      onElapsedChange?.(elapsed);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [onElapsedChange, state]);

  async function startRecording() {
    if (isCaptureActive || disabled) return;
    setError(null);
    setInterim("");
    setState("connecting");
    elapsedBaseRef.current = 0;
    setElapsedSec(0);
    onElapsedChange?.(0);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      startMeter(stream);
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
    if (!isCaptureActive) return;
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
    stopMeter();
    startedAtRef.current = null;
    elapsedBaseRef.current = 0;
    setElapsedSec(0);
    onElapsedChange?.(0);
    setState("idle");
  }

  function pauseRecording() {
    if (state !== "recording") return;
    const recorder = mediaRecorderRef.current;
    if (recorder?.state === "recording") {
      recorder.pause();
    }
    if (startedAtRef.current !== null) {
      elapsedBaseRef.current = Math.floor((Date.now() - startedAtRef.current) / 1000);
      setElapsedSec(elapsedBaseRef.current);
      onElapsedChange?.(elapsedBaseRef.current);
    }
    stopMeter();
    setState("paused");
  }

  async function resumeRecording() {
    if (state !== "paused") return;
    const recorder = mediaRecorderRef.current;
    if (recorder?.state === "paused") {
      recorder.resume();
    }
    if (streamRef.current) {
      startMeter(streamRef.current);
    }
    setState("recording");
  }

  function stopTracks() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    mediaRecorderRef.current = null;
  }

  function startMeter(stream: MediaStream) {
    stopMeter();
    const AudioContextCtor = window.AudioContext || (window as BrowserWindowWithAudioContext).webkitAudioContext;
    if (!AudioContextCtor) return;
    const audioContext = new AudioContextCtor();
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 128;
    analyser.smoothingTimeConstant = 0.82;
    audioContext.createMediaStreamSource(stream).connect(analyser);
    audioContextRef.current = audioContext;
    const data = new Uint8Array(analyser.fftSize);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let index = 0; index < data.length; index += 1) {
        const sample = data[index];
        const centered = (sample - 128) / 128;
        sum += centered * centered;
      }
      const rms = Math.min(1, Math.sqrt(sum / data.length) * 3.2);
      setLevels((current) => [...current.slice(1), Math.max(0.06, rms)]);
      animationFrameRef.current = window.requestAnimationFrame(tick);
    };
    tick();
  }

  function stopMeter() {
    if (animationFrameRef.current !== null) {
      window.cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    void audioContextRef.current?.close();
    audioContextRef.current = null;
    setLevels(Array.from({ length: 32 }, () => 0.08));
  }

  return (
    <>
      <div className="relative mx-auto mb-6 flex size-28 items-center justify-center">
        {isRecording ? <div className="klinia-pulse-ring absolute inset-0 rounded-full border border-ring" /> : null}
        <button
          className="relative z-10 flex size-24 items-center justify-center rounded-full border border-ring bg-card text-primary shadow-card transition-colors hover:bg-background active:bg-secondary"
          type="button"
          disabled={disabled || state === "connecting" || state === "stopping"}
          onClick={() => (isCaptureActive ? stopRecording() : void startRecording())}
          aria-label={isCaptureActive ? "Kaydı durdur" : "Kaydı başlat"}
        >
          {isCaptureActive ? <MicOff className="size-10" aria-hidden="true" /> : <Mic className="size-10" aria-hidden="true" />}
        </button>
      </div>

      <div className="space-y-4">
        <div>
          <h2 className="mb-2 text-xl font-semibold tracking-tight text-foreground">Görüşme Kaydı</h2>
          <p className="mx-auto max-w-xs text-sm leading-6 text-muted-foreground">
            Kaydı başlatın; analiz kayıt bittikten sonra çalışır.
          </p>
        </div>

        <Waveform levels={levels} active={isRecording} />

        <p className="text-xs font-medium tracking-wide text-primary" aria-live="polite">
          {statusText}{isCaptureActive ? ` · ${formatElapsed(elapsedSec)}` : ""}
        </p>
      </div>

      {showInlineControls ? (
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Button type="button" variant="outline" className="h-11 rounded-full border-border bg-card px-5 text-muted-foreground">
            <Square className="mr-2 size-4" />
            Duraklat
          </Button>
          <Button
            type="button"
            className="h-11 rounded-full bg-primary px-6 font-semibold text-primary-foreground shadow-card hover:bg-primary"
            disabled={disabled || state === "connecting" || state === "stopping"}
            onClick={() => (isCaptureActive ? stopRecording() : void startRecording())}
          >
            {isCaptureActive ? <Square className="mr-2 size-4" /> : <Mic className="mr-2 size-4" />}
            {isCaptureActive ? "Kaydı Bitir" : "Kaydı Başlat"}
          </Button>
        </div>
      ) : null}

      {interim ? (
        <div className="mt-5 rounded-2xl border border-border bg-secondary px-4 py-3 text-sm leading-6 text-muted-foreground">
          {interim}
        </div>
      ) : null}
      {error ? <p className="mt-4 text-sm font-medium text-destructive">{error}</p> : null}
    </>
  );
}

function Waveform({ levels, active }: { levels: number[]; active: boolean }) {
  const points = levels
    .map((level, index) => {
      const x = (index / Math.max(1, levels.length - 1)) * 160;
      const y = 22 - level * 18;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg className="mx-auto h-11 w-44 text-primary" viewBox="0 0 160 44" role="img" aria-label={active ? "Ses seviyesi" : "Sessiz kayıt çizgisi"}>
      <line x1="0" x2="160" y1="22" y2="22" stroke="currentColor" strokeOpacity="0.18" strokeWidth="1" />
      <polyline fill="none" points={points} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
    </svg>
  );
}

function formatElapsed(totalSec: number) {
  const minutes = Math.floor(totalSec / 60).toString().padStart(2, "0");
  const seconds = (totalSec % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function preferredMimeType() {
  if (typeof MediaRecorder === "undefined") return "";
  if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) return "audio/webm;codecs=opus";
  if (MediaRecorder.isTypeSupported("audio/webm")) return "audio/webm";
  return "";
}

function wsBase(apiBase: string) {
  if (apiBase.startsWith("/")) {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}${apiBase}`;
  }
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
