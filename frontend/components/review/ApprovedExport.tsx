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
    <main className="flex min-h-screen items-center justify-center bg-background px-6 py-12 text-foreground">
      <Card className="w-full max-w-xl border-border bg-card shadow-card">
        <CardContent className="p-8 text-center">
          <div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-primary/15 text-primary">
            <CheckCircle2 className="h-7 w-7" aria-hidden="true" />
          </div>
          <h1 className="mt-6 text-2xl font-semibold tracking-normal">Onaylandı · Klinik sisteminize aktarın</h1>
          {message ? <p className="mt-3 text-sm font-medium leading-6 text-muted-foreground">{message}</p> : null}
          <div className="mt-7 grid gap-3 sm:grid-cols-2">
            <Button className="h-11 rounded-lg bg-primary text-primary-foreground hover:bg-primary/80" type="button" onClick={onCopy}>
              <Copy className="mr-2 h-4 w-4" aria-hidden="true" />
              Kopyala
            </Button>
            <Button className="h-11 rounded-lg border-border bg-card text-foreground hover:bg-background" type="button" variant="outline" onClick={onDownloadTxt}>
              <Download className="mr-2 h-4 w-4" aria-hidden="true" />
              TXT indir
            </Button>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
