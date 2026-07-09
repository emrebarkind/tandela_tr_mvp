"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";
import { fetchPatients, type PatientSummary } from "@/lib/patients-api";

export default function PatientsPage() {
  const [query, setQuery] = useState("");
  const [patients, setPatients] = useState<PatientSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    setError(null);
    const timeout = window.setTimeout(() => {
      void fetchPatients(query)
        .then((result) => {
          if (active) setPatients(result);
        })
        .catch((caught) => {
          if (active) setError(errorMessage(caught));
        })
        .finally(() => {
          if (active) setIsLoading(false);
        });
    }, 180);
    return () => {
      active = false;
      window.clearTimeout(timeout);
    };
  }, [query]);

  const groupedPatients = useMemo(() => groupPatients(patients), [patients]);

  return (
    <main className="p-4 md:p-6">
      <div className="mx-auto max-w-6xl space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Hasta listesi</h2>
            <p className="mt-1 text-sm text-muted-foreground">Klinik görüşmeleri hasta bazında takip edin.</p>
          </div>
          <Link className="inline-flex h-9 items-center rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground" href="/session/new">
            + Yeni Görüşme
          </Link>
        </div>

        <div className="relative">
          <Search className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input
            className="h-14 rounded-xl pl-12 text-base"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Hasta adı veya dosya no ile ara"
            aria-label="Hasta adı veya dosya no ile ara"
          />
        </div>

        {error ? (
          <Card className="border-destructive/30">
            <CardContent className="p-4 text-sm text-destructive">{error}</CardContent>
          </Card>
        ) : null}

        {!isLoading && patients.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-start gap-4 p-8">
              <div>
                <h3 className="text-lg font-semibold">Henüz hasta kaydı yok. İlk görüşmeyi başlatın.</h3>
                <p className="mt-2 text-sm text-muted-foreground">Yeni görüşme tamamlandığında hasta ve seans bilgileri burada listelenecek.</p>
              </div>
              <Link className="inline-flex h-9 items-center rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground" href="/session/new">
                + Yeni Görüşme
              </Link>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableBody>
                  {groupedPatients.map((group) => (
                    <PatientGroup key={group.letter} group={group} />
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}
      </div>
    </main>
  );
}

function PatientGroup({ group }: { group: PatientGroup }) {
  return (
    <>
      <TableRow className="sticky top-16 z-10 bg-muted/95 hover:bg-muted/95">
        <TableCell colSpan={5} className="h-9 px-4 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
          {group.letter}
        </TableCell>
      </TableRow>
      {group.patients.map((patient) => (
        <TableRow key={patient.id} className="cursor-pointer">
          <TableCell className="px-4 py-4">
            <Link href={`/patients/${encodeURIComponent(patient.id)}`} className="block">
              <p className="font-semibold">{displayPatient(patient)}</p>
              <p className="mt-1 text-sm text-muted-foreground">Dosya no: {patient.external_id ?? "Yok"}</p>
            </Link>
          </TableCell>
          <TableCell className="hidden px-4 py-4 text-sm text-muted-foreground md:table-cell">
            {formatDate(patient.last_session_at)}
          </TableCell>
          <TableCell className="hidden px-4 py-4 text-sm text-muted-foreground md:table-cell">
            {patient.session_count} seans
          </TableCell>
          <TableCell className="hidden px-4 py-4 lg:table-cell">
            <ProcedureSummary procedures={patient.last_procedures} />
          </TableCell>
          <TableCell className="px-4 py-4 text-right">
            <StatusBadge status={patient.status} />
          </TableCell>
        </TableRow>
      ))}
    </>
  );
}

type PatientGroup = {
  letter: string;
  patients: PatientSummary[];
};

function groupPatients(patients: PatientSummary[]): PatientGroup[] {
  const sorted = [...patients].sort((left, right) =>
    displayPatient(left).localeCompare(displayPatient(right), "tr-TR"),
  );
  const groups = new Map<string, PatientSummary[]>();
  for (const patient of sorted) {
    const letter = displayPatient(patient).trim().charAt(0).toLocaleUpperCase("tr-TR") || "#";
    groups.set(letter, [...(groups.get(letter) ?? []), patient]);
  }
  return Array.from(groups.entries()).map(([letter, group]) => ({ letter, patients: group }));
}

function displayPatient(patient: PatientSummary) {
  return patient.initials?.trim() || patient.external_id?.trim() || "İsimsiz hasta";
}

function ProcedureSummary({ procedures }: { procedures: string[] }) {
  if (!procedures.length) return <span className="text-sm text-muted-foreground">İşlem yok</span>;
  const visible = procedures.slice(0, 2);
  const extra = procedures.length - visible.length;
  return (
    <div className="flex flex-wrap gap-1.5">
      {visible.map((procedure) => (
        <Badge key={procedure} variant="secondary" className="rounded-lg">
          {procedure}
        </Badge>
      ))}
      {extra > 0 ? <Badge variant="outline" className="rounded-lg">+{extra}</Badge> : null}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "approved" || status === "exported") return <Badge className="rounded-lg bg-emerald-100 text-emerald-900 hover:bg-emerald-100">Onaylı</Badge>;
  if (status === "no_sessions") return <Badge variant="secondary" className="rounded-lg">Yeni</Badge>;
  return <Badge className="rounded-lg bg-amber-100 text-amber-900 hover:bg-amber-100">Taslak</Badge>;
}

function formatDate(value: string | null) {
  if (!value) return "Görüşme yok";
  return new Intl.DateTimeFormat("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(new Date(value));
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Hasta listesi alınamadı.";
}
