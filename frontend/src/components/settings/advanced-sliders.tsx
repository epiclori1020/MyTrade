"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { PRESETS, SLIDER_CONFIG } from "@/lib/constants";
import type { PolicyMode, PresetId } from "@/lib/types";

interface AdvancedSlidersProps {
  mode: PolicyMode;
  preset: PresetId;
  overrides: Record<string, number>;
  onModeChange: (mode: PolicyMode) => void;
  onOverrideChange: (key: string, value: number) => void;
}

export function AdvancedSliders({
  mode,
  preset,
  overrides,
  onModeChange,
  onOverrideChange,
}: AdvancedSlidersProps) {
  const isAdvanced = mode === "ADVANCED";
  const confirmed = isAdvanced; // Toggle already implies confirmation

  function handleToggle(checked: boolean) {
    onModeChange(checked ? "ADVANCED" : "PRESET");
  }

  function getValue(key: string): number {
    if (isAdvanced && key in overrides) return overrides[key];
    return PRESETS[preset][key as keyof (typeof PRESETS)["beginner"]] as number;
  }

  // Compute core_pct from satellite_pct for display
  const satellitePct = getValue("satellite_pct");
  const corePct = 100 - satellitePct;

  return (
    <Card className={isAdvanced ? "border-destructive/30" : undefined}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Erweiterte Einstellungen</CardTitle>
          <Switch checked={isAdvanced} onCheckedChange={handleToggle} />
        </div>
      </CardHeader>

      {isAdvanced && (
        <CardContent className="space-y-6">
          <div className="flex items-start gap-2 rounded-md border border-destructive/20 bg-destructive/5 p-3">
            <Checkbox id="risk-ack" checked disabled className="mt-0.5" />
            <Label
              htmlFor="risk-ack"
              className="text-sm text-muted-foreground"
            >
              Ich verstehe, dass individuell angepasste Einstellungen das Risiko
              verändern können.
            </Label>
          </div>

          {confirmed && (
            <div className="grid gap-6 sm:grid-cols-2">
              {SLIDER_CONFIG.map((config) => {
                const val = getValue(config.key);
                const isSatellite = config.key === "satellite_pct";

                return (
                  <div key={config.key} className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Label className="text-sm">{config.label}</Label>
                      <span className="font-mono text-sm tabular-nums">
                        {val}
                        {config.unit}
                        {isSatellite && (
                          <span className="ml-1 text-muted-foreground">
                            (Core: {corePct}%)
                          </span>
                        )}
                      </span>
                    </div>
                    <Slider
                      value={[val]}
                      min={config.min}
                      max={config.max}
                      step={config.step}
                      onValueChange={([v]) =>
                        onOverrideChange(config.key, v)
                      }
                    />
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>
                        {config.min}
                        {config.unit}
                      </span>
                      <span>
                        {config.max}
                        {config.unit}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {config.microcopy}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}
