"use client";

import { useMemo, useState } from "react";
import { Send } from "lucide-react";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const AUTH_HEADERS = {
  "X-Tandela-Clinic-Id": process.env.NEXT_PUBLIC_TANDELA_CLINIC_ID ?? "dev-clinic",
  "X-Tandela-User-Id": process.env.NEXT_PUBLIC_TANDELA_USER_ID ?? "frontend-doctor",
  "X-Tandela-User-Role": process.env.NEXT_PUBLIC_TANDELA_USER_ROLE ?? "dentist",
};

type ChatMessage = {
  role: "user" | "assistant";
  text: string;
};

export function AssistantBar() {
  const pathname = usePathname();
  const context = useMemo(() => routeContext(pathname), [pathname]);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  async function sendMessage() {
    const message = input.trim();
    if (!message || isLoading) return;
    setInput("");
    setMessages((current) => [...current, { role: "user", text: message }]);
    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { ...AUTH_HEADERS, "Content-Type": "application/json" },
        body: JSON.stringify({ message, ...context }),
      });
      if (!response.ok) throw new Error(await response.text());
      const parsed = (await response.json()) as { answer?: string };
      setMessages((current) => [
        ...current,
        { role: "assistant", text: parsed.answer?.trim() || "Kayıtlarda bulunmuyor." },
      ]);
    } catch {
      setMessages((current) => [...current, { role: "assistant", text: "Kayıtlarda bulunmuyor." }]);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="fixed inset-x-0 bottom-0 z-30 border-t bg-background/95 px-4 py-3 backdrop-blur md:left-60">
      <div className="mx-auto max-w-5xl space-y-2">
        {messages.length ? (
          <ScrollArea className="max-h-40 rounded-xl border bg-card p-3">
            <div className="space-y-2 pr-3 text-sm">
              {messages.map((message, index) => (
                <div
                  key={`${message.role}-${index}`}
                  className={message.role === "assistant" ? "text-foreground" : "text-muted-foreground"}
                >
                  <span className="font-semibold">{message.role === "assistant" ? "Asistan" : "Siz"}: </span>
                  {message.text}
                </div>
              ))}
            </div>
          </ScrollArea>
        ) : null}
        <div className="flex items-center gap-2">
          <Input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void sendMessage();
            }}
            placeholder="Asistana kayıtlı klinik verilerden sorun"
            aria-label="Asistana sorun"
          />
          <Button type="button" onClick={() => void sendMessage()} disabled={isLoading || !input.trim()}>
            <Send className="mr-2 size-4" />
            Gönder
          </Button>
        </div>
      </div>
    </div>
  );
}

function routeContext(pathname: string): { patient_id?: string; session_id?: string } {
  const sessionMatch = /^\/session\/([^/]+)/.exec(pathname);
  if (sessionMatch?.[1] && sessionMatch[1] !== "new") return { session_id: decodeURIComponent(sessionMatch[1]) };
  const patientMatch = /^\/patients\/([^/]+)/.exec(pathname);
  if (patientMatch?.[1]) return { patient_id: decodeURIComponent(patientMatch[1]) };
  return {};
}
