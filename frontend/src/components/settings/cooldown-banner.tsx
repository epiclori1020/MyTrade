"use client";

import { Clock } from "lucide-react";
import { useEffect, useState } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { PRESET_META } from "@/lib/constants";
import type { PresetId } from "@/lib/types";

interface CooldownBannerProps {
  cooldownUntil: string;
  presetId: PresetId;
}

function formatRemaining(until: Date): string {
  const now = new Date();
  const diff = until.getTime() - now.getTime();
  if (diff <= 0) return "jetzt";

  const hours = Math.floor(diff / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export function CooldownBanner({ cooldownUntil, presetId }: CooldownBannerProps) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(interval);
  }, []);

  const until = new Date(cooldownUntil);
  if (until.getTime() <= now) return null;

  const presetLabel = PRESET_META[presetId]?.label ?? presetId;

  return (
    <Card className="border-unverified/40 bg-unverified/5">
      <CardContent className="flex items-center gap-3 py-3">
        <Clock className="h-4 w-4 shrink-0 text-unverified" />
        <p className="text-sm">
          Wechsel zu <span className="font-medium">{presetLabel}</span> aktiv ab{" "}
          <span className="font-mono">
            {until.toLocaleString("de-AT", {
              day: "2-digit",
              month: "2-digit",
              year: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
          <span className="ml-1 text-muted-foreground">
            (in {formatRemaining(until)})
          </span>
        </p>
      </CardContent>
    </Card>
  );
}
