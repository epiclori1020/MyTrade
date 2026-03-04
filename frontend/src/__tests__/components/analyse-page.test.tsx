import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// --- Child component mocks ---

vi.mock("@/components/analyse/ticker-search", () => ({
  TickerSearch: () => <div data-testid="ticker-search" />,
}))

vi.mock("@/components/analyse/investment-note", () => ({
  InvestmentNote: () => <div data-testid="investment-note" />,
}))

vi.mock("@/components/analyse/claims-list", () => ({
  ClaimsList: () => <div data-testid="claims-list" />,
}))

vi.mock("@/components/analyse/trade-form", () => ({
  TradeForm: () => <div data-testid="trade-form" />,
}))

vi.mock("@/components/analyse/pipeline-progress", () => ({
  PipelineProgress: () => <div data-testid="pipeline-progress" />,
}))

vi.mock("@/components/analyse/disclaimer", () => ({
  Disclaimer: () => <div data-testid="disclaimer" />,
}))

// --- Navigation mocks ---

const mockReplace = vi.fn()

vi.mock("next/navigation", () => ({
  useRouter: vi.fn(() => ({ replace: mockReplace })),
  useSearchParams: vi.fn(() => new URLSearchParams()),
}))

// --- API mock ---

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

// --- Pipeline hook mock ---

const defaultPipelineState = {
  state: "idle" as const,
  currentStep: 0,
  error: null,
  isRunning: false,
  analysisResult: null,
  claims: [],
  startAnalysis: vi.fn(),
  reset: vi.fn(),
}

vi.mock("@/hooks/use-analysis-pipeline", () => ({
  useAnalysisPipeline: vi.fn(() => defaultPipelineState),
}))

// --- Imports after mocks are defined ---

import AnalysePage from "@/app/(dashboard)/analyse/page"

// Minimal FundamentalOutput fixture that satisfies the type
const MOCK_FUNDAMENTAL_OUT = {
  business_model: {
    description: "test description",
    moat_assessment: "narrow",
    revenue_segments: "test segments",
  },
  financials: {
    revenue: null,
    net_income: null,
    free_cash_flow: null,
    eps: null,
    roe: null,
    roic: null,
  },
  valuation: {
    pe_ratio: null,
    pb_ratio: null,
    ev_ebitda: null,
    fcf_yield: null,
    assessment: "fairly_valued",
  },
  quality: {
    f_score: null,
    z_score: null,
    assessment: "solid",
  },
  moat_rating: "narrow",
  score: 75,
  risks: [],
  sources: [],
}

describe("AnalysePage", () => {
  let mockGet: ReturnType<typeof vi.fn>

  beforeEach(async () => {
    const mod = await import("@/lib/api")
    mockGet = vi.mocked(mod.api.get)
    vi.clearAllMocks()

    // Reset pipeline mock to default idle state before each test
    const { useAnalysisPipeline } = await import("@/hooks/use-analysis-pipeline")
    vi.mocked(useAnalysisPipeline).mockReturnValue({ ...defaultPipelineState })

    // Reset search params to empty
    const { useSearchParams } = await import("next/navigation")
    vi.mocked(useSearchParams).mockReturnValue(new URLSearchParams())
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("renders empty state when no URL params", async () => {
    // No ?id= or ?ticker= — pipeline idle, no loaded result
    render(<AnalysePage />)

    // Suspense resolves immediately in test env; wait for content to appear
    await waitFor(() => {
      expect(
        screen.getByText("Wähle einen Ticker und starte die Analyse."),
      ).toBeInTheDocument()
    })

    expect(mockGet).not.toHaveBeenCalled()
    expect(screen.queryByTestId("investment-note")).not.toBeInTheDocument()
  })

  it("shows loading skeleton when fetching existing analysis", async () => {
    const { useSearchParams } = await import("next/navigation")
    vi.mocked(useSearchParams).mockReturnValue(
      new URLSearchParams("id=test-123"),
    )

    // Never resolve so we stay in the loading state
    mockGet.mockReturnValue(new Promise(() => {}))

    render(<AnalysePage />)

    // loadingExisting is initialized to true via useState(() => !!searchParams.get("id"))
    await waitFor(() => {
      // When loadingExisting=true the "Analyse" heading is rendered along with
      // skeleton placeholders but the empty-state text is NOT shown
      expect(
        screen.queryByText("Wähle einen Ticker und starte die Analyse."),
      ).not.toBeInTheDocument()
    })

    // Skeletons are rendered (animate-pulse class applied by shadcn Skeleton)
    const skeletons = document.querySelectorAll(".animate-pulse")
    expect(skeletons.length).toBeGreaterThan(0)

    // api.get should have been called for both endpoints
    expect(mockGet).toHaveBeenCalledWith("/api/analyze/test-123")
    expect(mockGet).toHaveBeenCalledWith("/api/claims/test-123")
  })

  it("fetches and displays existing analysis when ?id= present", async () => {
    const { useSearchParams } = await import("next/navigation")
    vi.mocked(useSearchParams).mockReturnValue(
      new URLSearchParams("id=test-123&ticker=AAPL"),
    )

    const mockAnalysis = {
      analysis_id: "test-123",
      ticker: "AAPL",
      status: "completed",
      fundamental_out: MOCK_FUNDAMENTAL_OUT,
    }

    // First call: GET /api/analyze/test-123
    // Second call: GET /api/claims/test-123
    mockGet
      .mockResolvedValueOnce(mockAnalysis)
      .mockResolvedValueOnce({ claims: [] })

    render(<AnalysePage />)

    // After both promises resolve the investment note should appear
    await waitFor(() => {
      expect(screen.getByTestId("investment-note")).toBeInTheDocument()
    })

    expect(mockGet).toHaveBeenCalledWith("/api/analyze/test-123")
    expect(mockGet).toHaveBeenCalledWith("/api/claims/test-123")
  })

  it("shows pipeline result over loaded result (merge priority)", async () => {
    // Pipeline is complete with its own analysisResult — no ?id= in URL
    const { useAnalysisPipeline } = await import("@/hooks/use-analysis-pipeline")
    vi.mocked(useAnalysisPipeline).mockReturnValue({
      ...defaultPipelineState,
      state: "complete" as const,
      analysisResult: {
        analysis_id: "pipeline-1",
        ticker: "MSFT",
        status: "completed",
        fundamental_out: MOCK_FUNDAMENTAL_OUT,
      },
    })

    // useSearchParams stays at empty (no ?id=)
    render(<AnalysePage />)

    // showComplete = true because state === "complete"
    // effectiveResult = analysisResult (pipeline wins over loadedResult which is null)
    await waitFor(() => {
      expect(screen.getByTestId("investment-note")).toBeInTheDocument()
    })

    // api.get must NOT have been called (no ?id= param)
    expect(mockGet).not.toHaveBeenCalled()
  })
})
