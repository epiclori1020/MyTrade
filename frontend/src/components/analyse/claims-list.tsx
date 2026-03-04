"use client";

import {
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  Eye,
  XCircle,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { ClaimStatus, ClaimWithVerification } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ClaimsListProps {
  claims: ClaimWithVerification[];
}

const STATUS_CONFIG: Record<
  ClaimStatus,
  {
    label: string;
    className: string;
    icon: typeof CheckCircle;
  }
> = {
  verified: {
    label: "Verifiziert",
    className: "bg-verified/15 text-verified border-verified/30",
    icon: CheckCircle,
  },
  consistent: {
    label: "Konsistent",
    className: "bg-verified/15 text-verified border-verified/30",
    icon: CheckCircle,
  },
  unverified: {
    label: "Nicht geprüft",
    className: "bg-unverified/15 text-unverified border-unverified/30",
    icon: AlertTriangle,
  },
  manual_check: {
    label: "Prüfung nötig",
    className: "bg-unverified/15 text-unverified border-unverified/30",
    icon: Eye,
  },
  disputed: {
    label: "Beanstandet",
    className: "bg-disputed/15 text-disputed border-disputed/30",
    icon: XCircle,
  },
};

const TYPE_LABELS: Record<string, string> = {
  number: "Zahl",
  ratio: "Kennzahl",
  event: "Ereignis",
  opinion: "Meinung",
  forecast: "Prognose",
};

function StatusBadge({ status }: { status: ClaimStatus }) {
  const config = STATUS_CONFIG[status];
  const Icon = config.icon;

  return (
    <Badge variant="outline" className={config.className}>
      <Icon className="mr-1 h-3 w-3" />
      {config.label}
    </Badge>
  );
}

function ClaimRow({ claim }: { claim: ClaimWithVerification }) {
  const [open, setOpen] = useState(false);
  const status: ClaimStatus = claim.verification?.status ?? "unverified";
  const isDisputed = status === "disputed";

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div
        className={cn(
          "rounded-md border px-3 py-2.5",
          isDisputed && "border-disputed/30 bg-disputed/5",
        )}
      >
        <CollapsibleTrigger className="flex w-full items-start gap-3 text-left">
          <ChevronDown
            className={cn(
              "mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform",
              open && "rotate-180",
            )}
          />
          <div className="min-w-0 flex-1">
            <p className="text-sm">{claim.claim_text}</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <Badge variant="secondary" className="text-xs">
                {TYPE_LABELS[claim.claim_type] ?? claim.claim_type}
              </Badge>
              <StatusBadge status={status} />
              {claim.trade_critical && (
                <Badge
                  variant="outline"
                  className="border-accent/40 text-xs text-accent"
                >
                  Kritisch
                </Badge>
              )}
              <span className="text-xs text-muted-foreground">
                Tier {claim.tier}
              </span>
            </div>
          </div>
        </CollapsibleTrigger>

        <CollapsibleContent className="mt-3 border-t pt-3">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-xs text-muted-foreground">Primärwert</dt>
              <dd className="font-mono tabular-nums">
                {claim.value !== null ? String(claim.value) : "—"}
              </dd>
            </div>
            {claim.verification?.source_verification && (
              <>
                <div>
                  <dt className="text-xs text-muted-foreground">
                    Verifikationswert
                  </dt>
                  <dd className="font-mono tabular-nums">
                    {claim.verification.source_verification.value !== null
                      ? String(claim.verification.source_verification.value)
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Abweichung</dt>
                  <dd
                    className={cn(
                      "font-mono tabular-nums",
                      isDisputed && "text-disputed",
                    )}
                  >
                    {claim.verification.source_verification.deviation_pct !==
                    null
                      ? `${claim.verification.source_verification.deviation_pct.toFixed(1)}%`
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Quelle</dt>
                  <dd>
                    {claim.verification.source_verification.provider}
                  </dd>
                </div>
              </>
            )}
          </dl>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

export function ClaimsList({ claims }: ClaimsListProps) {
  const counts = claims.reduce(
    (acc, c) => {
      const status = c.verification?.status ?? "unverified";
      acc[status] = (acc[status] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Claims & Verifizierung</CardTitle>
        <p className="text-sm text-muted-foreground">
          {counts.verified ?? 0} verifiziert
          {counts.consistent ? `, ${counts.consistent} konsistent` : ""}
          {counts.unverified ? `, ${counts.unverified} nicht geprüft` : ""}
          {counts.manual_check
            ? `, ${counts.manual_check} Prüfung nötig`
            : ""}
          {counts.disputed ? `, ${counts.disputed} beanstandet` : ""}
        </p>
      </CardHeader>
      <CardContent className="space-y-2">
        {claims.map((claim) => (
          <ClaimRow key={claim.id} claim={claim} />
        ))}
        {claims.length === 0 && (
          <p className="py-4 text-center text-sm text-muted-foreground">
            Keine Claims vorhanden.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
