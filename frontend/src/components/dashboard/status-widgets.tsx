"use client";

import { Loader2, Shield, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type {
  BudgetStatus,
  KillSwitchEvaluateResponse,
  KillSwitchStatus,
} from "@/lib/types";
import { cn } from "@/lib/utils";

export function StatusWidgets() {
  const [killSwitch, setKillSwitch] = useState<KillSwitchStatus | null>(null);
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const [evaluating, setEvaluating] = useState(false);
  const [evalResult, setEvalResult] =
    useState<KillSwitchEvaluateResponse | null>(null);

  const [toggling, setToggling] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get<KillSwitchStatus>("/api/system/kill-switch"),
      api.get<BudgetStatus>("/api/system/budget"),
    ])
      .then(([ks, b]) => {
        setKillSwitch(ks);
        setBudget(b);
      })
      .catch(() => {
        // Graceful: widgets show error state individually
      })
      .finally(() => setLoading(false));
  }, []);

  async function handleEvaluate() {
    setEvaluating(true);
    try {
      const result = await api.post<KillSwitchEvaluateResponse>(
        "/api/system/kill-switch/evaluate",
        {},
      );
      setEvalResult(result);
      if (result.kill_switch_activated) {
        setKillSwitch((prev) =>
          prev ? { ...prev, active: true } : prev,
        );
        toast.warning("Kill-Switch wurde automatisch aktiviert");
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "System-Check fehlgeschlagen",
      );
    } finally {
      setEvaluating(false);
    }
  }

  async function handleToggleKillSwitch() {
    if (!killSwitch) return;
    setToggling(true);
    try {
      if (killSwitch.active) {
        await api.post("/api/system/kill-switch/deactivate", {});
        setKillSwitch({ active: false, reason: null, activated_at: null });
        toast.success("Kill-Switch deaktiviert");
      } else {
        await api.post("/api/system/kill-switch/activate", {
          reason: "manual_dashboard",
        });
        setKillSwitch({
          active: true,
          reason: "manual_dashboard",
          activated_at: new Date().toISOString(),
        });
        toast.info("Kill-Switch aktiviert");
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Aktion fehlgeschlagen",
      );
    } finally {
      setToggling(false);
    }
  }

  if (loading) {
    return (
      <div className="grid gap-4 sm:grid-cols-3">
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {/* Kill-Switch */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Kill-Switch</CardTitle>
            {killSwitch && (
              <Badge
                variant="outline"
                className={
                  killSwitch.active
                    ? "bg-disputed/15 text-disputed border-disputed/30"
                    : "bg-verified/15 text-verified border-verified/30"
                }
              >
                {killSwitch.active ? (
                  <>
                    <ShieldAlert className="mr-1 h-3 w-3" />
                    Aktiv
                  </>
                ) : (
                  <>
                    <Shield className="mr-1 h-3 w-3" />
                    Inaktiv
                  </>
                )}
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <Button
            variant="outline"
            size="sm"
            onClick={handleToggleKillSwitch}
            disabled={toggling || !killSwitch}
            className="w-full"
          >
            {toggling && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {killSwitch?.active ? "Deaktivieren" : "Aktivieren"}
          </Button>
        </CardContent>
      </Card>

      {/* Budget */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">API-Kosten MTD</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {budget ? (
            <>
              <div className="flex items-baseline justify-between">
                <span className="font-mono text-lg tabular-nums">
                  ${budget.total_spend.toFixed(2)}
                </span>
                <span className="text-sm text-muted-foreground">
                  / ${budget.total_cap.toFixed(0)}
                </span>
              </div>
              <Progress value={budget.utilization_pct} className="h-1.5" />
              {budget.warnings.length > 0 && (
                <div className="space-y-1">
                  {budget.warnings.map((w, i) => (
                    <p key={i} className="text-xs text-unverified">
                      {w}
                    </p>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Nicht verfügbar</p>
          )}
        </CardContent>
      </Card>

      {/* System Check + Verification Rate */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">System-Status</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {evalResult ? (
            <div className="space-y-1">
              <div className="flex items-baseline gap-2">
                <span
                  className={cn(
                    "font-mono text-lg tabular-nums",
                    (evalResult.rate_pct ?? 0) > 85
                      ? "text-verified"
                      : (evalResult.rate_pct ?? 0) >= 70
                        ? "text-unverified"
                        : "text-disputed",
                  )}
                >
                  {evalResult.rate_pct?.toFixed(0) ?? "—"}%
                </span>
                <span className="text-sm text-muted-foreground">
                  Verification Rate
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                {evalResult.verified_count ?? 0} / {evalResult.total_claims ?? 0} Claims
              </p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Noch nicht geprüft</p>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={handleEvaluate}
            disabled={evaluating}
            className="w-full"
          >
            {evaluating && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            System prüfen
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
