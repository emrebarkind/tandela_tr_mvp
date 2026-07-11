"use client";

import { ChevronsUpDown } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

type TranscriptDrawerProps = {
  transcriptText: string;
};

export function TranscriptDrawer({ transcriptText }: TranscriptDrawerProps) {
  return (
    <Collapsible className="rounded-lg border border-border bg-card shadow-card">
      <CollapsibleTrigger className="flex w-full items-center justify-between px-6 py-4 text-left text-sm font-semibold text-foreground">
        Transkripti Göster
        <ChevronsUpDown className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
      </CollapsibleTrigger>
      <CollapsibleContent className="border-t border-border px-6 py-4">
        <pre className="max-h-[320px] overflow-auto whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
          {transcriptText}
        </pre>
      </CollapsibleContent>
    </Collapsible>
  );
}
