"use client";

import { ArrowDown, ArrowUp, Check, Minus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PRESET_META, PRESETS } from "@/lib/constants";
import type { PresetId } from "@/lib/types";
import { cn } from "@/lib/utils";

interface PresetCardsProps {
  currentPreset: PresetId;
  selectedPreset: PresetId;
  onSelect: (preset: PresetId) => void;
  presets?: typeof PRESETS;
}

const RISK_COLORS = {
  low: "bg-verified/15 text-verified",
  medium: "bg-unverified/15 text-unverified",
  high: "bg-disputed/15 text-disputed",
} as const;

const RISK_LABELS = {
  low: "Niedriges Risiko",
  medium: "Mittleres Risiko",
  high: "Höheres Risiko",
} as const;

function getRiskDirection(from: PresetId, to: PresetId): "up" | "down" | "same" {
  const order: PresetId[] = ["beginner", "balanced", "active"];
  const fromIdx = order.indexOf(from);
  const toIdx = order.indexOf(to);
  if (toIdx > fromIdx) return "up";
  if (toIdx < fromIdx) return "down";
  return "same";
}

export function PresetCards({
  currentPreset,
  selectedPreset,
  onSelect,
  presets,
}: PresetCardsProps) {
  const effectivePresets = presets ?? PRESETS;
  const presetIds: PresetId[] = ["beginner", "balanced", "active"];

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        {presetIds.map((id) => {
          const meta = PRESET_META[id];
          const isSelected = selectedPreset === id;

          return (
            <Card
              key={id}
              role="button"
              tabIndex={0}
              onClick={() => onSelect(id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(id);
                }
              }}
              className={cn(
                "cursor-pointer transition-colors",
                isSelected
                  ? "border-accent ring-1 ring-accent/30"
                  : "hover:border-muted-foreground/30",
              )}
            >
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">{meta.label}</CardTitle>
                  {isSelected && (
                    <Check className="h-4 w-4 text-accent" />
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-2">
                <p className="text-sm text-muted-foreground">
                  {meta.description}
                </p>
                <div className="flex items-center gap-2">
                  <Badge
                    variant="outline"
                    className={RISK_COLORS[meta.risk]}
                  >
                    {RISK_LABELS[meta.risk]}
                  </Badge>
                  {"recommended" in meta && meta.recommended && (
                    <Badge variant="outline" className="border-accent/40 text-accent">
                      Empfohlen
                    </Badge>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Change info panel */}
      {selectedPreset !== currentPreset && (
        <div className="rounded-md border bg-muted/30 p-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            {getRiskDirection(currentPreset, selectedPreset) === "up" ? (
              <>
                <ArrowUp className="h-4 w-4 text-disputed" />
                <span className="text-disputed">Risiko steigt</span>
              </>
            ) : getRiskDirection(currentPreset, selectedPreset) === "down" ? (
              <>
                <ArrowDown className="h-4 w-4 text-verified" />
                <span className="text-verified">Risiko sinkt</span>
              </>
            ) : (
              <>
                <Minus className="h-4 w-4 text-muted-foreground" />
                <span>Keine Änderung</span>
              </>
            )}
          </div>
          <div className="mt-2 space-y-1 text-sm text-muted-foreground">
            {Object.entries(effectivePresets[selectedPreset]).map(([key, newVal]) => {
              const oldVal =
                effectivePresets[currentPreset][key as keyof (typeof PRESETS)["beginner"]];
              if (oldVal === newVal) return null;
              const label = key.replace(/_/g, " ").replace(/pct$/, "%");
              return (
                <p key={key}>
                  {label}: {String(oldVal)} → {String(newVal)}
                </p>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
