"use client";

import { RotateCcw } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { ClaimsList } from "@/components/analyse/claims-list";
import { Disclaimer } from "@/components/analyse/disclaimer";
import { InvestmentNote } from "@/components/analyse/investment-note";
import { PipelineProgress } from "@/components/analyse/pipeline-progress";
import { TickerSearch } from "@/components/analyse/ticker-search";
import { TradeForm } from "@/components/analyse/trade-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnalysisPipeline } from "@/hooks/use-analysis-pipeline";
import { api } from "@/lib/api";
import type { AnalyzeResponse, ClaimWithVerification } from "@/lib/types";

function AnalyseContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

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

  const [loadedResult, setLoadedResult] = useState<AnalyzeResponse | null>(
    null,
  );
  const [loadedClaims, setLoadedClaims] = useState<ClaimWithVerification[]>(
    [],
  );
  const [loadingExisting, setLoadingExisting] = useState(false);

  // Guard: only attempt the fetch once per mount — do not re-run when pipeline
  // state changes (startAnalysis calls reset() which clears pipeline state).
  const fetchAttempted = useRef(false);

  // Effect 1: On mount, if ?id= exists and pipeline is idle, fetch persisted result.
  useEffect(() => {
    const id = searchParams.get("id");
    if (!id || state !== "idle" || fetchAttempted.current) return;
    fetchAttempted.current = true;

    setLoadingExisting(true);

    Promise.all([
      api.get<AnalyzeResponse>(`/api/analyze/${id}`),
      api.get<{ claims: ClaimWithVerification[] }>(`/api/claims/${id}`),
    ])
      .then(([result, claimsData]) => {
        setLoadedResult(result);
        setLoadedClaims(claimsData.claims ?? []);
      })
      .catch(() => {
        // Silently ignore — show empty page
      })
      .finally(() => {
        setLoadingExisting(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Effect 2: When pipeline completes, push ticker + id into the URL.
  useEffect(() => {
    if (state === "complete" && analysisResult) {
      router.replace(
        `/analyse?ticker=${analysisResult.ticker}&id=${analysisResult.analysis_id}`,
        { scroll: false },
      );
    }
  }, [state, analysisResult, router]);

  // Merge pipeline output with loaded-from-DB output.
  const effectiveResult = analysisResult ?? loadedResult;
  const effectiveClaims =
    claims.length > 0 ? claims : loadedClaims;

  const showComplete =
    state === "complete" ||
    (state === "idle" && loadedResult !== null);

  const hasDisputedCritical = effectiveClaims.some(
    (c) => c.trade_critical && c.verification?.status === "disputed",
  );

  if (loadingExisting) {
    return (
      <div className="mx-auto max-w-5xl space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Analyse</h1>
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Analyse</h1>

      <TickerSearch
        onAnalyze={startAnalysis}
        disabled={isRunning}
        initialTicker={searchParams.get("ticker") ?? undefined}
      />

      {state !== "idle" && (
        <PipelineProgress
          state={state}
          currentStep={currentStep}
          error={error}
        />
      )}

      {showComplete && effectiveResult && (
        <>
          <InvestmentNote data={effectiveResult.fundamental_out} />
          <ClaimsList claims={effectiveClaims} />
          {!hasDisputedCritical && (
            <TradeForm
              ticker={effectiveResult.ticker}
              analysisId={effectiveResult.analysis_id}
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

      {state === "idle" && loadedResult === null && (
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

export default function AnalysePage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-5xl space-y-6">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-12" />
        </div>
      }
    >
      <AnalyseContent />
    </Suspense>
  );
}
