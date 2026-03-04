"use client";

import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { BrokerAccount } from "@/lib/types";

function formatCurrency(val: number): string {
  return val.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  });
}

export function PortfolioSummary() {
  const [account, setAccount] = useState<BrokerAccount | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<BrokerAccount>("/api/trades/account")
      .then(setAccount)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Fehler beim Laden"),
      )
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <Skeleton className="h-5 w-32" />
        </CardHeader>
        <CardContent className="space-y-2">
          <Skeleton className="h-8 w-40" />
          <Skeleton className="h-4 w-24" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-4">
          <p className="text-sm text-muted-foreground">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!account) return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Paper-Portfolio</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="font-mono text-2xl font-semibold tabular-nums">
          {formatCurrency(account.total_value)}
        </p>
        <div className="mt-2 flex gap-6 text-sm text-muted-foreground">
          <span>
            Cash:{" "}
            <span className="font-mono tabular-nums">
              {formatCurrency(account.cash)}
            </span>
          </span>
          <span>
            Kaufkraft:{" "}
            <span className="font-mono tabular-nums">
              {formatCurrency(account.buying_power)}
            </span>
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
