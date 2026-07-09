"use client";

import { CheckCircle2, Copy, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

type ApprovedExportProps = {
  message?: string | null;
  onCopy: () => void;
  onDownloadTxt: () => void;
};

export function ApprovedExport({ message, onCopy, onDownloadTxt }: ApprovedExportProps) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#F8F9F7] px-6 py-12 text-[#202422]">
      <Card className="w-full max-w-xl border-[#DDE3E0] bg-white shadow-sm">
        <CardContent className="p-8 text-center">
          <div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-[#4A7C63]/15 text-[#2D5A45]">
            <CheckCircle2 className="h-7 w-7" aria-hidden="true" />
          </div>
          <h1 className="mt-6 text-2xl font-semibold tracking-normal">Onaylandı · Klinik sisteminize aktarın</h1>
          {message ? <p className="mt-3 text-sm font-medium leading-6 text-[#6F7470]">{message}</p> : null}
          <div className="mt-7 grid gap-3 sm:grid-cols-2">
            <Button className="h-11 rounded-lg bg-[#2D5A45] text-white hover:bg-[#244A39]" type="button" onClick={onCopy}>
              <Copy className="mr-2 h-4 w-4" aria-hidden="true" />
              Kopyala
            </Button>
            <Button className="h-11 rounded-lg border-[#DDE3E0] bg-white text-[#202422] hover:bg-[#F8F9F7]" type="button" variant="outline" onClick={onDownloadTxt}>
              <Download className="mr-2 h-4 w-4" aria-hidden="true" />
              TXT indir
            </Button>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
