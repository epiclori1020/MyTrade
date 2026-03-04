"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PRESETS, SLIDER_CONFIG } from "@/lib/constants";
import type { PresetId } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ComparisonTableProps {
  activePreset: PresetId;
}

export function ComparisonTable({ activePreset }: ComparisonTableProps) {
  const presetIds: PresetId[] = ["beginner", "balanced", "active"];

  return (
    <div className="overflow-x-auto rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[200px]">Einstellung</TableHead>
            {presetIds.map((id) => (
              <TableHead
                key={id}
                className={cn(
                  "text-center",
                  id === activePreset && "bg-accent/5 font-medium",
                )}
              >
                {id === "beginner"
                  ? "Einsteiger"
                  : id === "balanced"
                    ? "Balanced"
                    : "Aktiv"}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {/* Core/Satellite row */}
          <TableRow>
            <TableCell className="font-medium">Core / Satellite</TableCell>
            {presetIds.map((id) => (
              <TableCell
                key={id}
                className={cn(
                  "text-center font-mono tabular-nums",
                  id === activePreset && "bg-accent/5",
                )}
              >
                {PRESETS[id].core_pct}/{PRESETS[id].satellite_pct}
              </TableCell>
            ))}
          </TableRow>

          {/* Slider-based rows (skip satellite_pct — already in Core/Satellite row) */}
          {SLIDER_CONFIG.filter((c) => c.key !== "satellite_pct").map((config) => (
            <TableRow key={config.key}>
              <TableCell className="font-medium">{config.label}</TableCell>
              {presetIds.map((id) => {
                const val =
                  PRESETS[id][config.key as keyof (typeof PRESETS)["beginner"]];
                return (
                  <TableCell
                    key={id}
                    className={cn(
                      "text-center font-mono tabular-nums",
                      id === activePreset && "bg-accent/5",
                    )}
                  >
                    {val}
                    {config.unit}
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
