"use client";

import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type TranscriptInputProps = {
  transcriptText: string;
  onTranscriptChange: (value: string) => void;
  onAnalyze: () => void;
  isLoading: boolean;
  canAnalyze: boolean;
  error?: string | null;
};

export function TranscriptInput({
  transcriptText,
  onTranscriptChange,
  onAnalyze,
  isLoading,
  canAnalyze,
  error,
}: TranscriptInputProps) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#F8F9F7] px-6 py-12 text-[#202422]">
      <Card className="w-full max-w-2xl border-[#DDE3E0] bg-white shadow-sm">
        <CardHeader className="space-y-3 px-8 pt-8">
          <CardTitle className="text-3xl font-semibold tracking-normal">Yeni Görüşme</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5 px-8 pb-8">
          <textarea
            className="min-h-[360px] w-full resize-y rounded-lg border border-[#DDE3E0] bg-[#F8F9F7] p-4 text-base leading-7 text-[#202422] outline-none transition focus:border-[#4A7C63] focus:bg-white"
            value={transcriptText}
            onChange={(event) => onTranscriptChange(event.target.value)}
            aria-label="Transkript"
            placeholder="A: Merhaba, şikayetiniz nedir?"
          />
          {error ? (
            <p className="rounded-lg border border-[#E49545]/30 bg-[#E49545]/10 px-4 py-3 text-sm font-medium text-[#7A6221]">
              {error}
            </p>
          ) : null}
          <Button
            className="h-12 w-full rounded-lg bg-[#2D5A45] text-base font-semibold text-white hover:bg-[#244A39]"
            type="button"
            onClick={onAnalyze}
            disabled={isLoading || !canAnalyze}
          >
            {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : null}
            Analiz Et
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}
