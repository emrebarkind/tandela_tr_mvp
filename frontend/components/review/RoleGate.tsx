"use client";

import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type Role = "dentist" | "patient" | "assistant_or_other" | "unknown";
type SpeakerStatus = "clear" | "review_needed" | "unresolved";

type Speaker = {
  id: string;
  role: Role;
  status: SpeakerStatus;
  utterances: number;
  sample: string;
  reason?: string;
};

type RoleGateProps = {
  speakers: Speaker[];
  isLoading: boolean;
  canApprove: boolean;
  onRoleChange: (speakerId: string, role: Role) => void;
  onApprove: () => void;
};

const roleLabels: Record<Role, string> = {
  dentist: "Hekim",
  patient: "Hasta",
  assistant_or_other: "Asistan / Diğer",
  unknown: "Bilinmiyor",
};

export function RoleGate({ speakers, isLoading, canApprove, onRoleChange, onApprove }: RoleGateProps) {
  return (
    <main className="min-h-screen bg-background px-6 py-12 text-foreground">
      <section className="mx-auto flex min-h-[calc(100vh-96px)] max-w-4xl items-center">
        <Card className="w-full border-secondary bg-card shadow-card">
          <CardHeader className="space-y-3 border-b border-border px-8 py-7">
            <Badge className="w-fit rounded-lg bg-secondary px-3 py-1.5 text-sm font-semibold text-foreground hover:bg-secondary">
              Konuşmacı rolleri belirsiz · Lütfen rolleri onaylayın
            </Badge>
            <CardTitle className="text-2xl font-semibold tracking-normal">Rol Onayı</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 px-8 py-7">
            {speakers.map((speaker) => (
              <div key={speaker.id} className="grid gap-4 rounded-lg border border-border bg-background p-4 md:grid-cols-[84px_220px_minmax(0,1fr)] md:items-center">
                <div>
                  <p className="text-sm font-semibold text-foreground">Konuşmacı {speaker.id}</p>
                  <p className="mt-1 text-xs font-medium text-muted-foreground">{speaker.utterances} ifade</p>
                </div>
                <Select value={speaker.role} onValueChange={(value) => onRoleChange(speaker.id, value as Role)}>
                  <SelectTrigger className="h-11 w-full rounded-lg border-border bg-card">
                    <SelectValue>{(value: Role) => roleLabels[value]}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="unknown">Bilinmiyor</SelectItem>
                    <SelectItem value="dentist">Hekim</SelectItem>
                    <SelectItem value="patient">Hasta</SelectItem>
                    <SelectItem value="assistant_or_other">Asistan / Diğer</SelectItem>
                  </SelectContent>
                </Select>
                <div className="space-y-1">
                  <p className="text-sm leading-6 text-foreground">{speaker.sample}</p>
                  {speaker.reason ? <p className="text-sm italic leading-6 text-muted-foreground">{speaker.reason}</p> : null}
                </div>
              </div>
            ))}
            <div className="pt-4">
              <Button
                className="h-12 w-full rounded-lg bg-primary text-base font-semibold text-primary-foreground hover:bg-primary/80"
                type="button"
                onClick={onApprove}
                disabled={isLoading || !canApprove}
              >
                {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : null}
                Rolleri Onayla
              </Button>
            </div>
          </CardContent>
        </Card>
      </section>
    </main>
  );
}
