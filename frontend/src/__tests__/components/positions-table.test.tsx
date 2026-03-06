import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { PositionsTable } from "@/components/dashboard/positions-table"

vi.mock("@/lib/api", () => ({
  api: { post: vi.fn(), get: vi.fn() },
}))

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

const MOCK_POSITION = {
  ticker: "AAPL",
  shares: 10,
  avg_price: 150,
  current_price: 155,
  market_value: 1550,
}

describe("PositionsTable", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("renders loading skeleton initially", async () => {
    const mod = await import("@/lib/api")
    vi.mocked(mod.api.get).mockReturnValue(new Promise(() => {}))

    render(<PositionsTable />)

    // In loading state the "Positionen" title is not yet shown
    expect(screen.queryByText("Positionen")).not.toBeInTheDocument()
    const skeletons = document.querySelectorAll("[data-slot='skeleton']")
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it("renders positions after successful load", async () => {
    const mod = await import("@/lib/api")
    vi.mocked(mod.api.get).mockResolvedValue({
      positions: [MOCK_POSITION],
      count: 1,
    })

    render(<PositionsTable />)

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument()
    })
  })

  it("renders empty state when no positions", async () => {
    const mod = await import("@/lib/api")
    vi.mocked(mod.api.get).mockResolvedValue({
      positions: [],
      count: 0,
    })

    render(<PositionsTable />)

    await waitFor(() => {
      expect(
        screen.getByText("Noch keine Paper-Trades ausgeführt."),
      ).toBeInTheDocument()
    })
  })

  it("shows error message on API failure", async () => {
    const mod = await import("@/lib/api")
    vi.mocked(mod.api.get).mockRejectedValue(new Error("Broker nicht erreichbar"))

    render(<PositionsTable />)

    await waitFor(() => {
      expect(screen.getByText("Broker nicht erreichbar")).toBeInTheDocument()
    })
  })

  it("calculates and displays P&L percentage", async () => {
    const mod = await import("@/lib/api")
    vi.mocked(mod.api.get).mockResolvedValue({
      positions: [
        {
          ticker: "MSFT",
          shares: 5,
          avg_price: 100,
          current_price: 110,
          market_value: 550,
        },
      ],
      count: 1,
    })

    render(<PositionsTable />)

    await waitFor(() => {
      // P&L = (110-100)/100 * 100 = +10.00%
      expect(screen.getByText("+10.00%")).toBeInTheDocument()
    })
  })
})
