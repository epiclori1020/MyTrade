import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useAnalysisPipeline } from "@/hooks/use-analysis-pipeline"

vi.mock("@/lib/api", () => ({
  api: {
    post: vi.fn(),
    get: vi.fn(),
  },
}))

const ANALYSIS_ID = "analysis-abc-123"

const mockPreCheckPass = { passed: true, violations: [], policy_snapshot: {} }
const mockPreCheckFail = {
  passed: false,
  violations: [{ rule: "forbidden_type", message: "Instrument verboten", severity: "blocking", current_value: null, limit_value: null }],
  policy_snapshot: {},
}
const mockCollect = { ticker: "AAPL", status: "ok", fundamentals_count: 5, prices_count: 100 }
const mockAnalysis = {
  analysis_id: ANALYSIS_ID,
  ticker: "AAPL",
  status: "completed",
  fundamental_out: {} as never,
}
const mockExtract = { analysis_id: ANALYSIS_ID, claims_count: 3, claims: [] }
const mockVerify = {
  analysis_id: ANALYSIS_ID,
  verified: 2,
  consistent: 1,
  unverified: 0,
  disputed: 0,
  manual_check: 0,
  total: 3,
}
const mockClaims = { claims: [{ id: "1", claim_text: "Revenue $100B" } as never] }

describe("useAnalysisPipeline", () => {
  let mockApi: { post: ReturnType<typeof vi.fn>; get: ReturnType<typeof vi.fn> }

  beforeEach(async () => {
    const mod = await import("@/lib/api")
    mockApi = mod.api as typeof mockApi
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it("starts in idle state", () => {
    const { result } = renderHook(() => useAnalysisPipeline())

    expect(result.current.state).toBe("idle")
    expect(result.current.currentStep).toBe(0)
    expect(result.current.error).toBeNull()
    expect(result.current.isRunning).toBe(false)
    expect(result.current.claims).toEqual([])
    expect(result.current.analysisResult).toBeNull()
  })

  it("transitions through pipeline states to complete", async () => {
    mockApi.post
      .mockResolvedValueOnce(mockPreCheckPass)  // pre-check
      .mockResolvedValueOnce(mockCollect)        // collect
      .mockResolvedValueOnce(mockAnalysis)       // analyze
      .mockResolvedValueOnce(mockExtract)        // extract-claims
      .mockResolvedValueOnce(mockVerify)         // verify
    mockApi.get.mockResolvedValueOnce(mockClaims)  // get claims

    const { result } = renderHook(() => useAnalysisPipeline())

    await act(async () => {
      await result.current.startAnalysis("AAPL")
    })

    expect(result.current.state).toBe("complete")
    expect(result.current.currentStep).toBe(5) // PIPELINE_STEPS.length
    expect(result.current.error).toBeNull()
    expect(result.current.isRunning).toBe(false)
    expect(result.current.analysisResult).toEqual(mockAnalysis)
    expect(result.current.claims).toEqual(mockClaims.claims)
    expect(result.current.verificationSummary).toEqual(mockVerify)

    // Verify API was called with correct endpoints
    expect(mockApi.post).toHaveBeenCalledWith("/api/policy/pre-check/AAPL", {})
    expect(mockApi.post).toHaveBeenCalledWith("/api/collect/AAPL", {})
    expect(mockApi.post).toHaveBeenCalledWith("/api/analyze/AAPL", {})
    expect(mockApi.post).toHaveBeenCalledWith(`/api/extract-claims/${ANALYSIS_ID}`, {})
    expect(mockApi.post).toHaveBeenCalledWith(`/api/verify/${ANALYSIS_ID}`, {})
    expect(mockApi.get).toHaveBeenCalledWith(`/api/claims/${ANALYSIS_ID}`)
  })

  it("handles pre-check failure → error state", async () => {
    mockApi.post.mockResolvedValueOnce(mockPreCheckFail)

    const { result } = renderHook(() => useAnalysisPipeline())

    await act(async () => {
      await result.current.startAnalysis("BADTICKER")
    })

    expect(result.current.state).toBe("error")
    expect(result.current.error).toBe("Instrument verboten")
    expect(result.current.policyViolations).toEqual(mockPreCheckFail)
    expect(result.current.isRunning).toBe(false)

    // Should not have proceeded past pre-check
    expect(mockApi.post).toHaveBeenCalledTimes(1)
    expect(mockApi.get).not.toHaveBeenCalled()
  })

  it("handles partial state when claims extraction fails", async () => {
    mockApi.post
      .mockResolvedValueOnce(mockPreCheckPass)
      .mockResolvedValueOnce(mockCollect)
      .mockResolvedValueOnce(mockAnalysis)
      .mockRejectedValueOnce(new Error("Extract failed")) // extract-claims throws

    const { result } = renderHook(() => useAnalysisPipeline())

    await act(async () => {
      await result.current.startAnalysis("AAPL")
    })

    expect(result.current.state).toBe("partial")
    expect(result.current.analysisResult).toEqual(mockAnalysis)
    expect(result.current.claims).toEqual([])
    expect(result.current.error).toBeNull()

    // Verify and get-claims should NOT have been called
    expect(mockApi.post).toHaveBeenCalledTimes(4)
    expect(mockApi.get).not.toHaveBeenCalled()
  })

  it("reset aborts running pipeline and returns to idle", async () => {
    // Make analyze hang indefinitely until we reset
    let resolveAnalyze: (v: unknown) => void
    const hangingPromise = new Promise((resolve) => { resolveAnalyze = resolve })

    mockApi.post
      .mockResolvedValueOnce(mockPreCheckPass)
      .mockResolvedValueOnce(mockCollect)
      .mockReturnValueOnce(hangingPromise) // analyze hangs

    const { result } = renderHook(() => useAnalysisPipeline())

    // Start analysis without awaiting — it will hang at analyze step
    act(() => {
      result.current.startAnalysis("AAPL").catch(() => {})
    })

    // Reset while pipeline is running
    act(() => {
      result.current.reset()
    })

    expect(result.current.state).toBe("idle")
    expect(result.current.isRunning).toBe(false)
    expect(result.current.currentStep).toBe(0)
    expect(result.current.claims).toEqual([])
    expect(result.current.analysisResult).toBeNull()

    // Resolve the hanging promise — the abortRef should prevent further state updates
    await act(async () => {
      resolveAnalyze!(mockAnalysis)
      await Promise.resolve()
    })

    // State should remain idle because abort was set
    expect(result.current.state).toBe("idle")
  })
})
