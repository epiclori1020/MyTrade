"use client";

import { useCallback, useRef, useState } from "react";

import { api } from "@/lib/api";
import { PIPELINE_STEPS } from "@/lib/constants";
import type {
  AnalyzeResponse,
  ClaimWithVerification,
  CollectResponse,
  ExtractClaimsResponse,
  PolicyCheckResponse,
  VerifyResponse,
} from "@/lib/types";

export type PipelineState =
  | "idle"
  | "pre-check"
  | "collecting"
  | "analyzing"
  | "extracting"
  | "verifying"
  | "complete"
  | "partial"
  | "error";

interface PipelineResult {
  state: PipelineState;
  currentStep: number;
  error: string | null;
  isRunning: boolean;
  analysisResult: AnalyzeResponse | null;
  claims: ClaimWithVerification[];
  verificationSummary: VerifyResponse | null;
  policyViolations: PolicyCheckResponse | null;
  startAnalysis: (ticker: string) => Promise<void>;
  reset: () => void;
}

export function useAnalysisPipeline(): PipelineResult {
  const [state, setState] = useState<PipelineState>("idle");
  const [currentStep, setCurrentStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [analysisResult, setAnalysisResult] =
    useState<AnalyzeResponse | null>(null);
  const [claims, setClaims] = useState<ClaimWithVerification[]>([]);
  const [verificationSummary, setVerificationSummary] =
    useState<VerifyResponse | null>(null);
  const [policyViolations, setPolicyViolations] =
    useState<PolicyCheckResponse | null>(null);

  const abortRef = useRef(false);

  const reset = useCallback(() => {
    abortRef.current = true;
    setState("idle");
    setCurrentStep(0);
    setError(null);
    setAnalysisResult(null);
    setClaims([]);
    setVerificationSummary(null);
    setPolicyViolations(null);
  }, []);

  const startAnalysis = useCallback(
    async (ticker: string) => {
      reset();
      abortRef.current = false;

      try {
        // Step 1: Pre-Policy Check
        setState("pre-check");
        setCurrentStep(0);

        const preCheck = await api.post<PolicyCheckResponse>(
          `/api/policy/pre-check/${ticker}`,
          {},
        );

        if (!preCheck.passed) {
          setPolicyViolations(preCheck);
          setError(
            preCheck.violations.map((v) => v.message).join(". ") ||
              "Policy-Verstoß erkannt",
          );
          setState("error");
          return;
        }

        if (abortRef.current) return;

        // Step 2: Collect Data
        setState("collecting");
        setCurrentStep(1);

        await api.post<CollectResponse>(`/api/collect/${ticker}`, {});

        if (abortRef.current) return;

        // Step 3: Analyze (long call — 30-120s)
        setState("analyzing");
        setCurrentStep(2);

        const analysis = await api.post<AnalyzeResponse>(
          `/api/analyze/${ticker}`,
          {},
        );
        setAnalysisResult(analysis);

        if (abortRef.current) return;

        // Step 4: Extract Claims
        setState("extracting");
        setCurrentStep(3);

        try {
          await api.post<ExtractClaimsResponse>(
            `/api/extract-claims/${analysis.analysis_id}`,
            {},
          );
        } catch {
          // Partial success — analysis done but claims extraction failed
          setState("partial");
          return;
        }

        if (abortRef.current) return;

        // Step 5: Verify Claims
        setState("verifying");
        setCurrentStep(4);

        let verifyResult: VerifyResponse;
        try {
          verifyResult = await api.post<VerifyResponse>(
            `/api/verify/${analysis.analysis_id}`,
            {},
          );
          setVerificationSummary(verifyResult);
        } catch {
          // Partial — analysis + claims done but verification failed
          // Still show claims without verification
          const claimsData = await api.get<{ claims: ClaimWithVerification[] }>(
            `/api/claims/${analysis.analysis_id}`,
          );
          setClaims(claimsData.claims);
          setState("partial");
          return;
        }

        if (abortRef.current) return;

        // Fetch claims with verification details
        const claimsData = await api.get<{ claims: ClaimWithVerification[] }>(
          `/api/claims/${analysis.analysis_id}`,
        );
        setClaims(claimsData.claims);

        setState("complete");
        setCurrentStep(PIPELINE_STEPS.length);
      } catch (err) {
        if (abortRef.current) return;
        const message =
          err instanceof Error ? err.message : "Ein Fehler ist aufgetreten";
        setError(message);
        setState("error");
      }
    },
    [reset],
  );

  return {
    state,
    currentStep,
    error,
    isRunning: !["idle", "complete", "partial", "error"].includes(state),
    analysisResult,
    claims,
    verificationSummary,
    policyViolations,
    startAnalysis,
    reset,
  };
}
