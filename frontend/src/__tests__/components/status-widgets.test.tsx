import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { StatusWidgets } from "@/components/dashboard/status-widgets"

vi.mock("@/lib/api", () => ({
  api: { post: vi.fn(), get: vi.fn() },
}))

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

const MOCK_KILL_SWITCH = { active: false, reason: null, activated_at: null }

const MOCK_BUDGET = {
  total_spend: 5.2,
  total_cap: 50,
  remaining: 44.8,
  utilization_pct: 10.4,
  tiers: {},
  warnings: [],
}

const MOCK_METRICS = {
  pipeline_error_rate: { rate_pct: 2, failed: 1, total: 50, detail: "ok" },
  avg_latency_seconds: { value: 45, total_runs: 10, detail: "ok" },
  verification_score: { rate_pct: 90, verified: 45, total: 50, detail: "ok" },
}

function setupMocks() {
  return vi.mocked(import("@/lib/api")).then((mod) => {
    vi.mocked(mod.api.get).mockImplementation((url: string) => {
      if (url.includes("kill-switch")) return Promise.resolve(MOCK_KILL_SWITCH)
      if (url.includes("budget")) return Promise.resolve(MOCK_BUDGET)
      if (url.includes("metrics")) return Promise.resolve(MOCK_METRICS)
      return Promise.reject(new Error("Unknown URL"))
    })
  })
}

describe("StatusWidgets", () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    await setupMocks()
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("renders loading skeletons initially", async () => {
    const mod = await import("@/lib/api")
    // Override to never resolve so loading state persists
    vi.mocked(mod.api.get).mockReturnValue(new Promise(() => {}))

    render(<StatusWidgets />)

    // Card titles should not appear during loading
    expect(screen.queryByText("Kill-Switch")).not.toBeInTheDocument()
    const skeletons = document.querySelectorAll("[data-slot='skeleton']")
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it("renders all three widget titles after load", async () => {
    render(<StatusWidgets />)

    await waitFor(() => {
      expect(screen.getByText("Kill-Switch")).toBeInTheDocument()
      expect(screen.getByText("API-Kosten MTD")).toBeInTheDocument()
      expect(screen.getByText("System-Status")).toBeInTheDocument()
    })
  })

  it("displays budget spend value", async () => {
    render(<StatusWidgets />)

    await waitFor(() => {
      // $5.20 formatted via toFixed(2)
      expect(screen.getByText("$5.20")).toBeInTheDocument()
    })
  })

  it("displays verification score metric", async () => {
    render(<StatusWidgets />)

    await waitFor(() => {
      // verification_score.rate_pct = 90 → "90%"
      expect(screen.getByText("90%")).toBeInTheDocument()
    })
  })

  it("renders system check button", async () => {
    render(<StatusWidgets />)

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /system prüfen/i }),
      ).toBeInTheDocument()
    })
  })

  it("renders available widgets when one endpoint fails (Promise.allSettled)", async () => {
    const mod = await import("@/lib/api")
    vi.mocked(mod.api.get).mockImplementation((url: string) => {
      if (url.includes("kill-switch")) return Promise.resolve(MOCK_KILL_SWITCH)
      if (url.includes("budget"))
        return Promise.reject(new Error("Budget service down"))
      if (url.includes("metrics")) return Promise.resolve(MOCK_METRICS)
      return Promise.reject(new Error("Unknown URL"))
    })

    render(<StatusWidgets />)

    await waitFor(() => {
      // Kill-Switch and System-Status should render normally
      expect(screen.getByText("Kill-Switch")).toBeInTheDocument()
      expect(screen.getByText("System-Status")).toBeInTheDocument()
      expect(screen.getByText("90%")).toBeInTheDocument()
      // Budget widget should show fallback (budget state is null)
      expect(screen.getByText("Nicht verfügbar")).toBeInTheDocument()
    })
  })
})
