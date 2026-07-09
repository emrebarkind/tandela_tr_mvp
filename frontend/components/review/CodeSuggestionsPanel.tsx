"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type CandidateCode = {
  code: string;
  procedure_name: string;
  category: string;
};

type CodeMatchResult = {
  code: string;
  match_state: string;
};

type ProcedureObject = {
  procedure_family: string;
  tooth_number_fdi?: number | null;
};

type ProcedureReview = {
  procedure: ProcedureObject;
  candidates: CandidateCode[];
  match_results: CodeMatchResult[];
  ambiguity_note?: string | null;
};

type CodeSuggestionsPanelProps = {
  procedures: ProcedureReview[];
  selectedCode: string;
  onSelectedCodeChange: (code: string) => void;
};

export function CodeSuggestionsPanel({ procedures, selectedCode, onSelectedCodeChange }: CodeSuggestionsPanelProps) {
  if (!procedures.length) return null;

  const rows = procedures.flatMap((procedure, procedureIndex) =>
    procedure.candidates.map((candidate) => ({
      key: `${procedureIndex}-${candidate.code}`,
      code: candidate.code,
      title: candidate.procedure_name,
      category: candidate.category,
      tooth: procedure.procedure.tooth_number_fdi,
      family: procedure.procedure.procedure_family,
      matchState: procedure.match_results.find((result) => result.code === candidate.code)?.match_state ?? "needs_review",
      ambiguityNote: procedure.ambiguity_note,
    })),
  );

  return (
    <Card className="overflow-hidden border-[#DDE3E0] bg-white shadow-sm">
      <CardHeader className="border-b border-[#DDE3E0] px-5 py-4">
        <CardTitle className="text-base font-semibold tracking-tight text-[#202422]">Kod Önerileri</CardTitle>
        <p className="mt-1 text-xs font-medium text-[#6F7470]">Kapalı kod veritabanı adayları</p>
      </CardHeader>
      <CardContent className="space-y-3 p-5">
        {rows.map((row) => (
          <button
            key={row.key}
            className={`w-full rounded-xl border p-4 text-left transition ${
              selectedCode === row.code
                ? "border-[#4A7C63] bg-[#4A7C63]/8"
                : "border-[#DDE3E0] bg-white hover:border-[#4A7C63]/45"
            }`}
            type="button"
            onClick={() => onSelectedCodeChange(row.code)}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-semibold text-[#202422]">{row.code}</p>
                <p className="mt-1 text-sm leading-6 text-[#6F7470]">{row.title}</p>
              </div>
              <MatchStateBadge state={row.matchState} />
            </div>
            <p className="mt-3 text-xs font-semibold uppercase tracking-[0.14em] text-[#6F7470]">
              {row.category} · FDI {row.tooth ?? "Belirsiz"}
            </p>
          </button>
        ))}
        {!selectedCode && rows[0]?.code ? (
          <Button className="h-11 w-full rounded-lg bg-[#2D5A45] text-white hover:bg-[#244A39]" type="button" onClick={() => onSelectedCodeChange(rows[0].code)}>
            İlk kodu seç
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

function MatchStateBadge({ state }: { state: string }) {
  const label = matchStateLabel(state);
  const className = matchStateClassName(state);
  return <Badge className={`shrink-0 rounded-lg px-3 py-1 text-xs font-semibold ${className}`}>{label}</Badge>;
}

function matchStateLabel(state: string) {
  if (state === "confirmed_by_documentation") return "Dokümantasyon Tam";
  if (state === "insufficient_documentation" || state === "needs_review") return "Eksik Bilgi";
  if (state === "ambiguous_multiple_candidates") return "Hekim Seçmeli";
  if (state === "no_match") return "Eşleşme Yok";
  return "Eksik Bilgi";
}

function matchStateClassName(state: string) {
  if (state === "confirmed_by_documentation") return "bg-[#4A7C63]/15 text-[#2D5A45]";
  if (state === "insufficient_documentation" || state === "needs_review") return "bg-[#E49545]/15 text-[#7A6221]";
  if (state === "ambiguous_multiple_candidates") return "bg-[#5A96C8]/15 text-[#315F80]";
  if (state === "no_match") return "bg-[#D8DDE5] text-[#59616B]";
  return "bg-[#E49545]/15 text-[#7A6221]";
}
