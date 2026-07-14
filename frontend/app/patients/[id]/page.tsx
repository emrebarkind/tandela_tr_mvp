"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Activity, FileText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { fetchPatientSessions, type PatientSessions } from "@/lib/patients-api";

export default function PatientDetailPage({ params }: { params: { id: string } }) {
  const [patient, setPatient] = useState<PatientSessions | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setError(null);
    void fetchPatientSessions(params.id)
      .then((result) => {
        if (active) setPatient(result);
      })
      .catch((caught) => {
        if (active) setError(caught instanceof Error ? caught.message : "Hasta detayı alınamadı.");
      });
    return () => {
      active = false;
    };
  }, [params.id]);

  return (
    <main className="p-4 md:p-6">
      <div className="mx-auto max-w-5xl space-y-5">
        {error ? (
          <Card className="border-destructive/30">
            <CardContent className="p-4 text-sm text-destructive">{error}</CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Hasta</p>
              <CardTitle className="mt-1 text-2xl">{patient ? displayPatient(patient) : "Yükleniyor"}</CardTitle>
              <p className="mt-2 text-sm text-muted-foreground">Dosya no: {patient?.external_id ?? "Yok"}</p>
            </div>
            <Link className="inline-flex h-9 items-center rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground" href={`/session/new?patient_id=${encodeURIComponent(params.id)}`}>
              Bu hastayla yeni görüşme
            </Link>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Seans geçmişi</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {patient && patient.sessions.length === 0 ? (
              <p className="text-sm text-muted-foreground">Bu hasta için kayıtlı seans yok.</p>
            ) : null}
            {patient?.sessions.map((session) => (
              <Link
                key={session.id}
                href={`/session/${encodeURIComponent(session.id)}`}
                className="block rounded-lg border bg-card p-4 transition-colors hover:bg-muted/40"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-semibold">{formatDate(session.started_at)}</p>
                      <SessionTypeBadge sessionType={session.session_type} />
                    </div>
                    <ProcedureSummary procedures={session.procedures} />
                  </div>
                  <StatusBadge status={session.status} />
                </div>
              </Link>
            ))}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}

function SessionTypeBadge({ sessionType }: { sessionType: "clinical_note" | "perio" }) {
  if (sessionType === "perio") {
    return (
      <Badge variant="secondary" className="gap-1.5 rounded-lg border border-border">
        <Activity className="size-3.5" aria-hidden="true" />
        Perio
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1.5 rounded-lg border-primary/30 bg-primary/10 text-primary">
      <FileText className="size-3.5" aria-hidden="true" />
      Klinik Not
    </Badge>
  );
}

function displayPatient(patient: PatientSessions) {
  return patient.initials?.trim() || patient.external_id?.trim() || "İsimsiz hasta";
}

function ProcedureSummary({ procedures }: { procedures: string[] }) {
  if (!procedures.length) return <p className="mt-1 text-sm text-muted-foreground">İşlem yok</p>;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {procedures.slice(0, 3).map((procedure) => (
        <Badge key={procedure} variant="secondary" className="rounded-lg">
          {procedure}
        </Badge>
      ))}
      {procedures.length > 3 ? <Badge variant="outline" className="rounded-lg">+{procedures.length - 3}</Badge> : null}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "approved" || status === "exported") return <Badge className="rounded-lg bg-emerald-100 text-emerald-900 hover:bg-emerald-100">Onaylı</Badge>;
  return <Badge className="rounded-lg bg-amber-100 text-amber-900 hover:bg-amber-100">Taslak</Badge>;
}

function formatDate(value: string | null) {
  if (!value) return "Tarih yok";
  return new Intl.DateTimeFormat("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(new Date(value));
}
