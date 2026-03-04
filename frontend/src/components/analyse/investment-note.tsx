"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { DataPoint, FundamentalOutput } from "@/lib/types";
import { cn } from "@/lib/utils";

interface InvestmentNoteProps {
  data: FundamentalOutput;
}

function formatValue(dp: DataPoint | null): string {
  if (!dp || dp.value === null) return "N/A";
  switch (dp.unit) {
    case "USD":
      return `$${dp.value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    case "USD_B":
      return `$${dp.value.toFixed(1)}B`;
    case "pct":
      return `${dp.value.toFixed(1)}%`;
    case "ratio":
      return dp.value.toFixed(1);
    default:
      return String(dp.value);
  }
}

function getAssessment(score: number, valuation: string) {
  const isUndervalued = valuation.toLowerCase().includes("undervalued");
  const isFairlyValued = valuation.toLowerCase().includes("fairly_valued");

  if (score >= 70 && isUndervalued) return { label: "Kaufkandidat", variant: "default" as const, className: "bg-verified/15 text-verified border-verified/30" };
  if (score >= 70 && isFairlyValued) return { label: "Attraktiv", variant: "default" as const, className: "bg-verified/10 text-verified border-verified/20" };
  if (score >= 40) return { label: "Fair bewertet", variant: "secondary" as const, className: "" };
  return { label: "Nicht attraktiv", variant: "default" as const, className: "bg-disputed/15 text-disputed border-disputed/30" };
}

function getMoatBadge(moat: string) {
  switch (moat.toLowerCase()) {
    case "wide":
      return { label: "Wide Moat", className: "bg-verified/15 text-verified border-verified/30" };
    case "narrow":
      return { label: "Narrow Moat", className: "bg-unverified/15 text-unverified border-unverified/30" };
    default:
      return { label: "No Moat", className: "" };
  }
}

function ScoreGauge({ score }: { score: number }) {
  const color =
    score >= 70 ? "text-verified" : score >= 40 ? "text-unverified" : "text-disputed";

  return (
    <div className="flex items-center gap-3">
      <div className="relative flex h-16 w-16 items-center justify-center">
        <svg className="h-16 w-16 -rotate-90" viewBox="0 0 64 64">
          <circle
            cx="32"
            cy="32"
            r="28"
            fill="none"
            stroke="currentColor"
            strokeWidth="4"
            className="text-muted/50"
          />
          <circle
            cx="32"
            cy="32"
            r="28"
            fill="none"
            stroke="currentColor"
            strokeWidth="4"
            strokeDasharray={`${(score / 100) * 175.9} 175.9`}
            strokeLinecap="round"
            className={color}
          />
        </svg>
        <span className={cn("absolute font-mono text-lg font-bold", color)}>
          {score}
        </span>
      </div>
    </div>
  );
}

interface FinancialRow {
  label: string;
  dataPoint: DataPoint | null;
}

export function InvestmentNote({ data }: InvestmentNoteProps) {
  const assessment = getAssessment(data.score, data.valuation.assessment);
  const moat = getMoatBadge(data.moat_rating);

  const financialRows: FinancialRow[] = [
    { label: "Revenue", dataPoint: data.financials.revenue },
    { label: "Net Income", dataPoint: data.financials.net_income },
    { label: "Free Cash Flow", dataPoint: data.financials.free_cash_flow },
    { label: "EPS", dataPoint: data.financials.eps },
    { label: "ROE", dataPoint: data.financials.roe },
    { label: "ROIC", dataPoint: data.financials.roic },
    { label: "P/E Ratio", dataPoint: data.valuation.pe_ratio },
    { label: "P/B Ratio", dataPoint: data.valuation.pb_ratio },
    { label: "EV/EBITDA", dataPoint: data.valuation.ev_ebitda },
    { label: "FCF Yield", dataPoint: data.valuation.fcf_yield },
    { label: "F-Score", dataPoint: data.quality.f_score },
    { label: "Z-Score", dataPoint: data.quality.z_score },
  ];

  return (
    <div className="space-y-4">
      {/* Header: Score + Assessment + Moat */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center gap-4">
            <ScoreGauge score={data.score} />
            <div className="space-y-1">
              <Badge variant={assessment.variant} className={assessment.className}>
                {assessment.label}
              </Badge>
              <Badge variant="outline" className={cn("ml-2", moat.className)}>
                {moat.label}
              </Badge>
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* These + Geschäftsmodell */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Geschäftsmodell</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p>{data.business_model.description}</p>
          <div>
            <span className="font-medium text-muted-foreground">
              Moat-Bewertung:{" "}
            </span>
            {data.business_model.moat_assessment}
          </div>
          <div>
            <span className="font-medium text-muted-foreground">
              Umsatzsegmente:{" "}
            </span>
            {data.business_model.revenue_segments}
          </div>
        </CardContent>
      </Card>

      {/* Risiken */}
      {data.risks.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Risiken</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {data.risks.map((risk, i) => (
                <li key={i} className="flex gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-disputed/60" />
                  {risk}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Key Financials Table */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Kennzahlen</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Kennzahl</TableHead>
                <TableHead className="text-right">Wert</TableHead>
                <TableHead className="hidden sm:table-cell">Quelle</TableHead>
                <TableHead className="hidden sm:table-cell">Zeitraum</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {financialRows.map((row) => (
                <TableRow key={row.label}>
                  <TableCell className="font-medium">{row.label}</TableCell>
                  <TableCell
                    className={cn(
                      "text-right font-mono tabular-nums",
                      !row.dataPoint?.value && "text-muted-foreground",
                    )}
                  >
                    {formatValue(row.dataPoint)}
                  </TableCell>
                  <TableCell className="hidden text-muted-foreground sm:table-cell">
                    {row.dataPoint?.source ?? "—"}
                  </TableCell>
                  <TableCell className="hidden text-muted-foreground sm:table-cell">
                    {row.dataPoint?.period ?? "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Quality Assessment */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Qualitätsbewertung</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {data.quality.f_score && (
            <div>
              <span className="font-medium">Piotroski F-Score: </span>
              <span className="font-mono">
                {data.quality.f_score.value ?? "N/A"}
              </span>
              <span className="text-muted-foreground"> / 9</span>
            </div>
          )}
          {data.quality.z_score && (
            <div>
              <span className="font-medium">Altman Z-Score: </span>
              <span className="font-mono">
                {data.quality.z_score.value?.toFixed(2) ?? "N/A"}
              </span>
            </div>
          )}
          <p className="text-muted-foreground">{data.quality.assessment}</p>
        </CardContent>
      </Card>

      {/* Valuation Assessment */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Bewertung</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm">{data.valuation.assessment}</p>
        </CardContent>
      </Card>
    </div>
  );
}
