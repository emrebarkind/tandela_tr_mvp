"use client";

import { ArrowLeft, ArrowRight, Check, Circle, Dot } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type PipelineStageState = "done" | "current" | "blocked" | "idle";

export type PipelineStage = {
  id: string;
  label: string;
  description?: string;
  state: PipelineStageState;
  disabled?: boolean;
};

type PipelineStageBarProps = {
  stages: PipelineStage[];
  activeStageId: string;
  onSelectStage: (stageId: string) => void;
};

export function PipelineStageBar({ stages, activeStageId, onSelectStage }: PipelineStageBarProps) {
  const activeIndex = Math.max(
    0,
    stages.findIndex((stage) => stage.id === activeStageId),
  );
  const previous = stages
    .slice(0, activeIndex)
    .reverse()
    .find((stage) => !stage.disabled);
  const next = stages.slice(activeIndex + 1).find((stage) => !stage.disabled);

  return (
    <section className="sticky top-[3.75rem] z-20 border-b bg-background/95 px-4 py-3 backdrop-blur md:px-6">
      <div className="mx-auto flex max-w-7xl flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Pipeline</p>
            <h2 className="text-sm font-semibold text-foreground">Ses kaydından hekim onayına kadar tüm aşamalar</h2>
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!previous}
              onClick={() => previous && onSelectStage(previous.id)}
            >
              <ArrowLeft className="mr-2 size-4" />
              Geri
            </Button>
            <Button type="button" size="sm" disabled={!next} onClick={() => next && onSelectStage(next.id)}>
              İlerle
              <ArrowRight className="ml-2 size-4" />
            </Button>
          </div>
        </div>

        <div className="flex gap-2 overflow-x-auto pb-1">
          {stages.map((stage) => (
            <button
              key={stage.id}
              type="button"
              disabled={stage.disabled}
              onClick={() => onSelectStage(stage.id)}
              className={cn(
                "flex min-w-[150px] items-center gap-2 rounded-xl border bg-card px-3 py-2 text-left shadow-sm transition",
                stage.id === activeStageId && "border-[#4A7C63] ring-2 ring-[#4A7C63]/15",
                stage.disabled && "cursor-not-allowed opacity-45",
                !stage.disabled && "hover:border-[#4A7C63]/60",
              )}
            >
              <StageIcon state={stage.state} />
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold">{stage.label}</span>
                {stage.description ? (
                  <span className="block truncate text-xs text-muted-foreground">{stage.description}</span>
                ) : null}
              </span>
              {stage.state === "blocked" ? (
                <Badge variant="outline" className="ml-auto border-amber-300 bg-amber-50 text-amber-800">
                  Onay
                </Badge>
              ) : null}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function StageIcon({ state }: { state: PipelineStageState }) {
  if (state === "done") {
    return <Check className="size-4 shrink-0 text-[#4A7C63]" />;
  }
  if (state === "current") {
    return <Dot className="size-5 shrink-0 text-[#2D5A45]" />;
  }
  if (state === "blocked") {
    return <Circle className="size-4 shrink-0 fill-amber-400 text-amber-500" />;
  }
  return <Circle className="size-4 shrink-0 text-muted-foreground" />;
}
