import { cleanup, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { TradeForm } from "@/components/analyse/trade-form"

vi.mock("@/lib/api", () => ({
  api: {
    post: vi.fn(),
    get: vi.fn(),
  },
}))

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}))

const DEFAULT_PROPS = {
  ticker: "AAPL",
  analysisId: "analysis-test-123",
}

describe("TradeForm", () => {
  let mockPost: ReturnType<typeof vi.fn>

  beforeEach(async () => {
    const mod = await import("@/lib/api")
    mockPost = vi.mocked(mod.api.post)
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("renders trade form with ticker and input fields", () => {
    render(<TradeForm {...DEFAULT_PROPS} />)

    expect(screen.getByText("Trade-Plan")).toBeInTheDocument()
    // Use getAllBy since placeholders might match multiple renders — but after cleanup there's only one
    expect(screen.getAllByPlaceholderText("z.B. 10")).toHaveLength(1)
    expect(screen.getAllByPlaceholderText("z.B. 180.50")).toHaveLength(1)
    expect(screen.getAllByPlaceholderText("z.B. 160.00")).toHaveLength(1)
    expect(screen.getByRole("button", { name: /policy prüfen/i })).toBeInTheDocument()
  })

  it("calls policy full-check on submit with correct payload", async () => {
    const user = userEvent.setup()

    mockPost.mockResolvedValueOnce({
      passed: true,
      violations: [],
      policy_snapshot: {},
    })

    render(<TradeForm {...DEFAULT_PROPS} />)

    const sharesInput = screen.getByPlaceholderText("z.B. 10")
    const priceInput = screen.getByPlaceholderText("z.B. 180.50")
    const policyButton = screen.getByRole("button", { name: /policy prüfen/i })

    await user.type(sharesInput, "10")
    await user.type(priceInput, "180.50")
    await user.click(policyButton)

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/policy/full-check", {
        ticker: "AAPL",
        action: "BUY",
        shares: 10,
        price: 180.5,
        analysis_id: "analysis-test-123",
        stop_loss: null,
      })
    })
  })

  it("shows proposed trade after successful propose", async () => {
    const user = userEvent.setup()

    mockPost
      .mockResolvedValueOnce({ passed: true, violations: [], policy_snapshot: {} })
      .mockResolvedValueOnce({
        trade_id: "trade-123",
        status: "proposed",
        ticker: "AAPL",
        action: "BUY" as const,
        shares: 10,
        price: 180.5,
      })

    render(<TradeForm {...DEFAULT_PROPS} />)

    await user.type(screen.getByPlaceholderText("z.B. 10"), "10")
    await user.type(screen.getByPlaceholderText("z.B. 180.50"), "180.50")
    await user.click(screen.getByRole("button", { name: /policy prüfen/i }))

    await waitFor(() => {
      expect(screen.getByText("Trade erlaubt")).toBeInTheDocument()
    })

    const proposeButton = screen.getByRole("button", { name: /trade vorschlagen/i })
    await user.click(proposeButton)

    // After propose, the form hides and approve/reject appear
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /bestätigen/i })).toBeInTheDocument()
      expect(screen.getByRole("button", { name: /ablehnen/i })).toBeInTheDocument()
    })

    expect(mockPost).toHaveBeenCalledWith(
      "/api/trades/propose",
      expect.objectContaining({ ticker: "AAPL", action: "BUY" }),
    )
  })

  it("calls approve endpoint with trade_id (not id)", async () => {
    const user = userEvent.setup()

    mockPost
      .mockResolvedValueOnce({ passed: true, violations: [], policy_snapshot: {} })
      .mockResolvedValueOnce({ trade_id: "trade-abc-456", status: "proposed" })
      .mockResolvedValueOnce({ trade_id: "trade-abc-456", status: "executed" })

    render(<TradeForm {...DEFAULT_PROPS} />)

    await user.type(screen.getByPlaceholderText("z.B. 10"), "5")
    await user.type(screen.getByPlaceholderText("z.B. 180.50"), "200.00")
    await user.click(screen.getByRole("button", { name: /policy prüfen/i }))

    await waitFor(() => screen.getByText("Trade erlaubt"))
    await user.click(screen.getByRole("button", { name: /trade vorschlagen/i }))
    await waitFor(() => screen.getByRole("button", { name: /bestätigen/i }))

    // Click the "Bestätigen" button to open AlertDialog
    await user.click(screen.getByRole("button", { name: /bestätigen/i }))

    // Click the AlertDialog action button to confirm
    await waitFor(() =>
      screen.getByRole("button", { name: /bestätigen/i }),
    )
    // After the dialog opens, there are now two "Bestätigen" buttons (trigger + action)
    const allConfirmButtons = screen.getAllByRole("button", { name: /bestätigen/i })
    await user.click(allConfirmButtons[allConfirmButtons.length - 1])

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/api/trades/trade-abc-456/approve",
        {},
      )
    })

    // Also verify it used trade_id, not something else
    const approveCall = mockPost.mock.calls.find((c) =>
      (c[0] as string).includes("/approve"),
    )
    expect(approveCall?.[0]).toBe("/api/trades/trade-abc-456/approve")
  })
})
