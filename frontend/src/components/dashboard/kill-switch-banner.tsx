"use client";

import { Loader2, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { KillSwitchStatus } from "@/lib/types";

export function KillSwitchBanner() {
  const [status, setStatus] = useState<KillSwitchStatus | null>(null);
  const [deactivating, setDeactivating] = useState(false);

  useEffect(() => {
    api
      .get<KillSwitchStatus>("/api/system/kill-switch")
      .then(setStatus)
      .catch(() => {
        // Graceful: banner won't show
      });
  }, []);

  if (!status?.active) return null;

  async function handleDeactivate() {
    setDeactivating(true);
    try {
      await api.post("/api/system/kill-switch/deactivate", {});
      setStatus({ active: false, reason: null, activated_at: null });
      toast.success("Kill-Switch deaktiviert");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Deaktivierung fehlgeschlagen",
      );
    } finally {
      setDeactivating(false);
    }
  }

  return (
    <Card className="border-destructive bg-destructive/5">
      <CardContent className="flex flex-col items-start gap-3 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-destructive" />
          <p className="text-sm font-medium text-destructive">
            System pausiert — Kill-Switch aktiv. Keine neuen Analysen oder
            Trades möglich.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleDeactivate}
          disabled={deactivating}
        >
          {deactivating && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Deaktivieren
        </Button>
      </CardContent>
    </Card>
  );
}
