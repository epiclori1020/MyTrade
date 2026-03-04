"use client";

import { CheckCircle, Circle, Loader2, XCircle } from "lucide-react";

import { Progress } from "@/components/ui/progress";
import { PIPELINE_STEPS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import type { PipelineState } from "@/hooks/use-analysis-pipeline";

interface PipelineProgressProps {
  state: PipelineState;
  currentStep: number;
  error: string | null;
}

function getStepStatus(
  index: number,
  currentStep: number,
  state: PipelineState,
): "done" | "active" | "pending" | "error" {
  if (state === "error" && index === currentStep) return "error";
  if (index < currentStep) return "done";
  if (index === currentStep && state !== "complete" && state !== "partial")
    return "active";
  return "pending";
}

function StepIcon({ status }: { status: "done" | "active" | "pending" | "error" }) {
  switch (status) {
    case "done":
      return <CheckCircle className="h-5 w-5 text-verified" />;
    case "active":
      return <Loader2 className="h-5 w-5 animate-spin text-accent" />;
    case "error":
      return <XCircle className="h-5 w-5 text-disputed" />;
    case "pending":
      return <Circle className="h-5 w-5 text-muted-foreground/40" />;
  }
}

export function PipelineProgress({
  state,
  currentStep,
  error,
}: PipelineProgressProps) {
  const progressPct =
    state === "complete"
      ? 100
      : state === "partial"
        ? 60
        : (currentStep / PIPELINE_STEPS.length) * 100;

  return (
    <div className="space-y-4">
      <Progress value={progressPct} className="h-1.5" />

      {/* Desktop: horizontal */}
      <div className="hidden items-center justify-between sm:flex">
        {PIPELINE_STEPS.map((step, i) => {
          const status = getStepStatus(i, currentStep, state);
          return (
            <div key={step.key} className="flex items-center gap-2">
              <StepIcon status={status} />
              <span
                className={cn(
                  "text-sm",
                  status === "active" && "font-medium text-foreground",
                  status === "done" && "text-verified",
                  status === "pending" && "text-muted-foreground",
                  status === "error" && "text-disputed",
                )}
              >
                {step.label}
              </span>
              {i < PIPELINE_STEPS.length - 1 && (
                <div
                  className={cn(
                    "mx-2 h-px w-8",
                    i < currentStep ? "bg-verified/40" : "bg-border",
                  )}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Mobile: vertical */}
      <div className="space-y-2 sm:hidden">
        {PIPELINE_STEPS.map((step, i) => {
          const status = getStepStatus(i, currentStep, state);
          return (
            <div key={step.key} className="flex items-center gap-3">
              <StepIcon status={status} />
              <span
                className={cn(
                  "text-sm",
                  status === "active" && "font-medium text-foreground",
                  status === "done" && "text-verified",
                  status === "pending" && "text-muted-foreground",
                  status === "error" && "text-disputed",
                )}
              >
                {step.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Hint for long-running step */}
      {state === "analyzing" && (
        <p className="text-center text-sm text-muted-foreground">
          Dies kann 1–2 Minuten dauern. Bitte lass diese Seite offen.
        </p>
      )}

      {/* Error message */}
      {state === "error" && error && (
        <p className="text-sm text-disputed">{error}</p>
      )}
    </div>
  );
}
