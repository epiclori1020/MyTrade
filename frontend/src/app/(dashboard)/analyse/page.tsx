"use client";

import { RotateCcw } from "lucide-react";

import { ClaimsList } from "@/components/analyse/claims-list";
import { Disclaimer } from "@/components/analyse/disclaimer";
import { InvestmentNote } from "@/components/analyse/investment-note";
import { PipelineProgress } from "@/components/analyse/pipeline-progress";
import { TickerSearch } from "@/components/analyse/ticker-search";
import { TradeForm } from "@/components/analyse/trade-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useAnalysisPipeline } from "@/hooks/use-analysis-pipeline";

export default function AnalysePage() {
  const {
    state,
    currentStep,
    error,
    isRunning,
    analysisResult,
    claims,
    startAnalysis,
    reset,
  } = useAnalysisPipeline();

  const hasDisputedCritical = claims.some(
    (c) => c.trade_critical && c.verification?.status === "disputed",
  );

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Analyse</h1>

      <TickerSearch onAnalyze={startAnalysis} disabled={isRunning} />

      {state !== "idle" && (
        <PipelineProgress
          state={state}
          currentStep={currentStep}
          error={error}
        />
      )}

      {state === "complete" && analysisResult && (
        <>
          <InvestmentNote data={analysisResult.fundamental_out} />
          <ClaimsList claims={claims} />
          {!hasDisputedCritical && (
            <TradeForm
              ticker={analysisResult.ticker}
              analysisId={analysisResult.analysis_id}
            />
          )}
          {hasDisputedCritical && (
            <Card className="border-disputed/30 bg-disputed/5">
              <CardContent className="py-4">
                <p className="text-sm text-disputed">
                  Trade blockiert: Ein oder mehrere kritische Claims sind
                  beanstandet. Bitte prüfe die Daten manuell.
                </p>
              </CardContent>
            </Card>
          )}
          <Disclaimer />
        </>
      )}

      {state === "partial" && analysisResult && (
        <>
          <InvestmentNote data={analysisResult.fundamental_out} />
          <Card className="border-unverified/40">
            <CardContent className="py-4">
              <p className="text-sm text-unverified">
                Analyse teilweise abgeschlossen. Claims konnten nicht
                extrahiert oder verifiziert werden. Trade-Erstellung nicht
                möglich.
              </p>
            </CardContent>
          </Card>
        </>
      )}

      {state === "error" && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-8">
            <p className="text-sm text-disputed">
              {error ?? "Ein Fehler ist aufgetreten."}
            </p>
            <Button variant="outline" size="sm" onClick={reset}>
              <RotateCcw className="mr-2 h-4 w-4" />
              Erneut versuchen
            </Button>
          </CardContent>
        </Card>
      )}

      {state === "idle" && (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground">
              Wähle einen Ticker und starte die Analyse.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
