"use client";

import {
  Activity,
  Clock,
  Loader2,
  Shield,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
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
  SystemMetrics,
} from "@/lib/types";
import { cn } from "@/lib/utils";

export function StatusWidgets() {
  const [killSwitch, setKillSwitch] = useState<KillSwitchStatus | null>(null);
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  const [evaluating, setEvaluating] = useState(false);
  const [evalResult, setEvalResult] =
    useState<KillSwitchEvaluateResponse | null>(null);

  const [toggling, setToggling] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get<KillSwitchStatus>("/api/system/kill-switch"),
      api.get<BudgetStatus>("/api/system/budget"),
      api.get<SystemMetrics>("/api/system/metrics"),
    ])
      .then(([ks, b, m]) => {
        setKillSwitch(ks);
        setBudget(b);
        setMetrics(m);
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
      if (result.triggered) {
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
          {killSwitch?.active ? (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  variant="outline"
                  disabled={toggling}
                  className="w-full min-h-[44px]"
                >
                  {toggling && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Deaktivieren
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Kill-Switch deaktivieren?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Das System wird wieder neue Analysen und Trades erlauben.
                    Stelle sicher, dass die Ursache der Aktivierung behoben ist.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                  <AlertDialogAction onClick={handleToggleKillSwitch}>
                    Deaktivieren
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          ) : (
            <Button
              variant="outline"
              onClick={handleToggleKillSwitch}
              disabled={toggling || !killSwitch}
              className="w-full min-h-[44px]"
            >
              {toggling && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Aktivieren
            </Button>
          )}
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

      {/* System Status + Metrics */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">System-Status</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Always-visible metrics */}
          {metrics ? (
            <div className="space-y-2">
              <MetricRow
                icon={<ShieldCheck className="h-3.5 w-3.5" />}
                label="Verification"
                value={`${metrics.verification_score.rate_pct.toFixed(0)}%`}
                sub={`${metrics.verification_score.verified ?? 0}/${metrics.verification_score.total} Claims`}
                color={
                  metrics.verification_score.rate_pct > 85
                    ? "text-verified"
                    : metrics.verification_score.rate_pct >= 70
                      ? "text-unverified"
                      : "text-disputed"
                }
              />
              <MetricRow
                icon={<Activity className="h-3.5 w-3.5" />}
                label="Fehlerrate"
                value={`${metrics.pipeline_error_rate.rate_pct.toFixed(0)}%`}
                sub={`${metrics.pipeline_error_rate.failed ?? 0}/${metrics.pipeline_error_rate.total} fehlgeschlagen`}
                color={
                  metrics.pipeline_error_rate.rate_pct < 5
                    ? "text-verified"
                    : metrics.pipeline_error_rate.rate_pct <= 10
                      ? "text-unverified"
                      : "text-disputed"
                }
              />
              <MetricRow
                icon={<Clock className="h-3.5 w-3.5" />}
                label="Latenz"
                value={`${metrics.avg_latency_seconds.value.toFixed(0)}s`}
                sub={`${metrics.avg_latency_seconds.total_runs} Runs`}
                color={
                  metrics.avg_latency_seconds.value < 60
                    ? "text-verified"
                    : metrics.avg_latency_seconds.value <= 120
                      ? "text-unverified"
                      : "text-disputed"
                }
              />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Metriken nicht verfügbar</p>
          )}

          {/* Trigger breakdown after evaluation */}
          {evalResult && (
            <div className="rounded-md border p-2 space-y-1 text-xs">
              <TriggerRow label="Drawdown" trigger={evalResult.triggers.drawdown} />
              <TriggerRow label="Broker CB" trigger={evalResult.triggers.broker_cb} />
              <TriggerRow label="Verification" trigger={evalResult.triggers.verification_rate} />
            </div>
          )}

          <Button
            variant="outline"
            onClick={handleEvaluate}
            disabled={evaluating}
            className="w-full min-h-[44px]"
          >
            {evaluating && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            System prüfen
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function MetricRow({
  icon,
  label,
  value,
  sub,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
  color: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-1.5 text-muted-foreground">
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <div className="text-right">
        <span className={cn("font-mono text-sm tabular-nums", color)}>
          {value}
        </span>
        <p className="text-[10px] text-muted-foreground leading-tight">{sub}</p>
      </div>
    </div>
  );
}

function TriggerRow({
  label,
  trigger,
}: {
  label: string;
  trigger: { triggered: boolean; detail?: string };
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <Badge
        variant="outline"
        className={cn(
          "text-[10px] px-1.5 py-0",
          trigger.triggered
            ? "bg-disputed/15 text-disputed border-disputed/30"
            : "bg-verified/15 text-verified border-verified/30",
        )}
      >
        {trigger.triggered ? "Ausgelöst" : "OK"}
      </Badge>
    </div>
  );
}
