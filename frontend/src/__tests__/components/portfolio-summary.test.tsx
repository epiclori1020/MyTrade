import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { PortfolioSummary } from "@/components/dashboard/portfolio-summary"

vi.mock("@/lib/api", () => ({
  api: { post: vi.fn(), get: vi.fn() },
}))

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

describe("PortfolioSummary", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("renders loading skeleton initially", async () => {
    // Never resolve so loading state persists
    const mod = await import("@/lib/api")
    vi.mocked(mod.api.get).mockReturnValue(new Promise(() => {}))

    render(<PortfolioSummary />)

    // In loading state "Paper-Portfolio" title should not yet appear
    expect(screen.queryByText("Paper-Portfolio")).not.toBeInTheDocument()
    // Skeleton elements rendered via Skeleton component (div with data-slot="skeleton")
    const skeletons = document.querySelectorAll("[data-slot='skeleton']")
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it("renders account data after successful load", async () => {
    const mod = await import("@/lib/api")
    vi.mocked(mod.api.get).mockResolvedValue({
      total_value: 100000,
      cash: 25000,
      buying_power: 50000,
    })

    render(<PortfolioSummary />)

    await waitFor(() => {
      expect(screen.getByText("Paper-Portfolio")).toBeInTheDocument()
    })
  })

  it("renders error message on API failure", async () => {
    const mod = await import("@/lib/api")
    vi.mocked(mod.api.get).mockRejectedValue(new Error("Network error"))

    render(<PortfolioSummary />)

    await waitFor(() => {
      expect(screen.getByText("Network error")).toBeInTheDocument()
    })
  })

  it("displays formatted currency values", async () => {
    const mod = await import("@/lib/api")
    vi.mocked(mod.api.get).mockResolvedValue({
      total_value: 100000,
      cash: 25000,
      buying_power: 50000,
    })

    render(<PortfolioSummary />)

    await waitFor(() => {
      // total_value formatted as currency — $100,000.00
      expect(screen.getByText("$100,000.00")).toBeInTheDocument()
      // cash
      expect(screen.getByText("$25,000.00")).toBeInTheDocument()
      // buying_power
      expect(screen.getByText("$50,000.00")).toBeInTheDocument()
    })
  })
})
