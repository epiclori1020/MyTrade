"use client";

import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { AdvancedSliders } from "@/components/settings/advanced-sliders";
import { ComparisonTable } from "@/components/settings/comparison-table";
import { CooldownBanner } from "@/components/settings/cooldown-banner";
import { PresetCards } from "@/components/settings/preset-cards";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { PRESETS } from "@/lib/constants";
import type { PolicyMode, PresetId, PresetsResponse, UserPolicySettings } from "@/lib/types";

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Server state (last saved)
  const [serverState, setServerState] = useState<UserPolicySettings | null>(
    null,
  );

  // Runtime presets fetched from backend (fallback to local constant)
  const [presets, setPresets] = useState(PRESETS);

  // Local state (editable)
  const [mode, setMode] = useState<PolicyMode>("BEGINNER");
  const [presetId, setPresetId] = useState<PresetId>("beginner");
  const [overrides, setOverrides] = useState<Record<string, number>>({});
  const [cooldownUntil, setCooldownUntil] = useState<string | null>(null);

  const isDirty =
    serverState !== null &&
    (mode !== serverState.policy_mode ||
      presetId !== serverState.preset_id ||
      JSON.stringify(overrides) !== JSON.stringify(serverState.policy_overrides));

  const loadSettings = useCallback(async () => {
    try {
      const [data, presetsData] = await Promise.all([
        api.get<UserPolicySettings>("/api/policy/settings"),
        api.get<PresetsResponse>("/api/policy/presets"),
      ]);
      setServerState(data);
      setMode(data.policy_mode);
      setPresetId(data.preset_id);
      setOverrides(data.policy_overrides);
      setCooldownUntil(data.cooldown_until);
      setPresets(presetsData.presets as typeof PRESETS);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Einstellungen konnten nicht geladen werden",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  function handlePresetSelect(id: PresetId) {
    setPresetId(id);
    if (mode === "BEGINNER") setMode("PRESET");
    // Preset change clears overrides (per spec)
    if (id !== serverState?.preset_id) {
      setOverrides({});
      if (mode === "ADVANCED") setMode("PRESET");
    }
  }

  function handleModeChange(newMode: PolicyMode) {
    setMode(newMode);
    if (newMode !== "ADVANCED") {
      setOverrides({});
    }
  }

  function handleOverrideChange(key: string, value: number) {
    setOverrides((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    setSaving(true);
    try {
      const result = await api.put<UserPolicySettings>(
        "/api/policy/settings",
        {
          policy_mode: mode,
          preset_id: presetId,
          policy_overrides: mode === "ADVANCED" ? overrides : {},
        },
      );
      setServerState(result);
      setCooldownUntil(result.cooldown_until);
      toast.success("Einstellungen gespeichert");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Speichern fehlgeschlagen",
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-3 sm:grid-cols-3">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-4xl space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight">
          Einstellungen
        </h1>
        <div className="rounded-md border border-disputed/30 bg-disputed/5 p-4">
          <p className="text-sm text-disputed">{error}</p>
          <Button variant="outline" size="sm" className="mt-2" onClick={loadSettings}>
            Erneut versuchen
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Einstellungen</h1>

      {cooldownUntil && (
        <CooldownBanner cooldownUntil={cooldownUntil} presetId={presetId} />
      )}

      <section className="space-y-4">
        <h2 className="text-lg font-medium">Risikoprofil</h2>
        <PresetCards
          currentPreset={serverState?.preset_id ?? "beginner"}
          selectedPreset={presetId}
          onSelect={handlePresetSelect}
          presets={presets}
        />
        <ComparisonTable activePreset={presetId} presets={presets} />
      </section>

      <section>
        <AdvancedSliders
          mode={mode}
          preset={presetId}
          overrides={overrides}
          onModeChange={handleModeChange}
          onOverrideChange={handleOverrideChange}
          presets={presets}
        />
      </section>

      <Button
        onClick={handleSave}
        disabled={!isDirty || saving}
        className="bg-accent text-accent-foreground hover:bg-accent/90"
      >
        {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
        {saving ? "Speichern…" : "Änderungen speichern"}
      </Button>
    </div>
  );
}
