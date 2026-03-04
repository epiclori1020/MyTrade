"use client";

import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import type { Position } from "@/lib/types";
import { cn } from "@/lib/utils";

export function PositionsTable() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Position[]>("/api/trades/positions")
      .then(setPositions)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Fehler beim Laden"),
      )
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <Skeleton className="h-5 w-24" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Positionen</CardTitle>
      </CardHeader>
      <CardContent>
        {error ? (
          <p className="text-sm text-muted-foreground">{error}</p>
        ) : positions.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            Noch keine Paper-Trades ausgeführt.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Ticker</TableHead>
                  <TableHead className="text-right">Stück</TableHead>
                  <TableHead className="text-right">Ø Preis</TableHead>
                  <TableHead className="text-right">Aktuell</TableHead>
                  <TableHead className="text-right">Marktwert</TableHead>
                  <TableHead className="text-right">P&L</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {positions.map((pos) => {
                  const pnl = pos.avg_price > 0
                    ? ((pos.current_price - pos.avg_price) / pos.avg_price) * 100
                    : 0;
                  return (
                    <TableRow key={pos.ticker}>
                      <TableCell className="font-mono font-medium">
                        {pos.ticker}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {pos.shares}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        ${pos.avg_price.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        ${pos.current_price.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        ${pos.market_value.toFixed(2)}
                      </TableCell>
                      <TableCell
                        className={cn(
                          "text-right font-mono tabular-nums",
                          pnl >= 0 ? "text-verified" : "text-disputed",
                        )}
                      >
                        {pnl >= 0 ? "+" : ""}
                        {pnl.toFixed(2)}%
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
