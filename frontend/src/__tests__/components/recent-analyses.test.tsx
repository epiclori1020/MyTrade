import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { RecentAnalyses } from "@/components/dashboard/recent-analyses"
import type { AnalysisRun } from "@/lib/types"

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode
    href: string
  }) => <a href={href}>{children}</a>,
}))

const MOCK_RUN: AnalysisRun = {
  id: "test-run-1",
  ticker: "AAPL",
  started_at: "2026-03-01T10:00:00Z",
  status: "completed",
  fundamental_out: { score: 85 } as unknown as AnalysisRun["fundamental_out"],
  confidence: 85,
  recommendation: "BUY",
}

describe("RecentAnalyses", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("renders empty state with link to analyse", () => {
    render(<RecentAnalyses data={[]} />)

    expect(
      screen.getByText("Noch keine Analysen vorhanden."),
    ).toBeInTheDocument()
    const link = screen.getByRole("link", { name: "Erste Analyse starten" })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute("href", "/analyse")
  })

  it("renders analysis runs with ticker and date", () => {
    render(<RecentAnalyses data={[MOCK_RUN]} />)

    expect(screen.getByText("AAPL")).toBeInTheDocument()
    // Status badge
    expect(screen.getByText("completed")).toBeInTheDocument()
  })

  it("renders score badge for high score", () => {
    render(<RecentAnalyses data={[MOCK_RUN]} />)

    // Score 85 → high badge — displayed as "85"
    expect(screen.getByText("85")).toBeInTheDocument()
  })

  it("links to analyse page with correct params", () => {
    render(<RecentAnalyses data={[MOCK_RUN]} />)

    // The run row is an <a> tag wrapping the whole row
    const links = screen.getAllByRole("link")
    const analyseLink = links.find(
      (l) =>
        l.getAttribute("href")?.includes("ticker=") &&
        l.getAttribute("href")?.includes("id="),
    )
    expect(analyseLink).toBeDefined()
    expect(analyseLink!.getAttribute("href")).toContain("ticker=AAPL")
    expect(analyseLink!.getAttribute("href")).toContain("id=test-run-1")
  })
})
