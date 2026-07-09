"use client";

import { ChevronsUpDown } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

type TranscriptDrawerProps = {
  transcriptText: string;
};

export function TranscriptDrawer({ transcriptText }: TranscriptDrawerProps) {
  return (
    <Collapsible className="rounded-lg border border-[#DDE3E0] bg-white shadow-sm">
      <CollapsibleTrigger className="flex w-full items-center justify-between px-6 py-4 text-left text-sm font-semibold text-[#202422]">
        Transkripti Göster
        <ChevronsUpDown className="h-4 w-4 text-[#6F7470]" aria-hidden="true" />
      </CollapsibleTrigger>
      <CollapsibleContent className="border-t border-[#DDE3E0] px-6 py-4">
        <pre className="max-h-[320px] overflow-auto whitespace-pre-wrap text-sm leading-6 text-[#6F7470]">
          {transcriptText}
        </pre>
      </CollapsibleContent>
    </Collapsible>
  );
}
