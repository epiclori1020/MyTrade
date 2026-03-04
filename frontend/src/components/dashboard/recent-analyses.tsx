import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AnalysisRun } from "@/lib/types";
import { cn } from "@/lib/utils";

interface RecentAnalysesProps {
  data: AnalysisRun[];
}

function getScoreBadge(score: number | null | undefined) {
  if (score == null) return null;
  if (score >= 70)
    return { label: `${score}`, className: "bg-verified/15 text-verified" };
  if (score >= 40)
    return { label: `${score}`, className: "bg-unverified/15 text-unverified" };
  return { label: `${score}`, className: "bg-disputed/15 text-disputed" };
}

export function RecentAnalyses({ data }: RecentAnalysesProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Letzte Analysen</CardTitle>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <div className="py-4 text-center">
            <p className="text-sm text-muted-foreground">
              Noch keine Analysen vorhanden.
            </p>
            <Link
              href="/analyse"
              className="mt-1 inline-block text-sm text-accent underline-offset-4 hover:underline"
            >
              Erste Analyse starten
            </Link>
          </div>
        ) : (
          <div className="space-y-2">
            {data.map((run) => {
              const score = run.fundamental_out?.score;
              const badge = getScoreBadge(score);
              const date = new Date(run.started_at).toLocaleDateString(
                "de-AT",
                { day: "2-digit", month: "2-digit", year: "numeric" },
              );

              return (
                <Link
                  key={run.id}
                  href={`/analyse?ticker=${run.ticker}&id=${run.id}`}
                  className="flex items-center justify-between rounded-md border px-3 py-2 transition-colors hover:bg-muted/50"
                >
                  <div className="flex items-center gap-3">
                    <span className="font-mono font-medium">{run.ticker}</span>
                    <span className="text-sm text-muted-foreground">
                      {date}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    {badge && (
                      <Badge
                        variant="outline"
                        className={cn("font-mono", badge.className)}
                      >
                        {badge.label}
                      </Badge>
                    )}
                    <Badge variant="secondary" className="text-xs">
                      {run.status}
                    </Badge>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
