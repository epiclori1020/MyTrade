import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { KillSwitchBanner } from "@/components/dashboard/kill-switch-banner"

vi.mock("@/lib/api", () => ({
  api: { post: vi.fn(), get: vi.fn() },
}))

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

describe("KillSwitchBanner", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("renders nothing when kill-switch inactive", async () => {
    const mod = await import("@/lib/api")
    vi.mocked(mod.api.get).mockResolvedValue({
      active: false,
      reason: null,
      activated_at: null,
    })

    const { container } = render(<KillSwitchBanner />)

    // Wait for the effect to resolve and state to settle
    await waitFor(() => {
      // Component returns null when not active — container should be empty
      expect(
        screen.queryByText(/system pausiert/i),
      ).not.toBeInTheDocument()
    })
    expect(container.firstChild).toBeNull()
  })

  it("renders banner when kill-switch active", async () => {
    const mod = await import("@/lib/api")
    vi.mocked(mod.api.get).mockResolvedValue({
      active: true,
      reason: "manual",
      activated_at: "2026-03-06T10:00:00Z",
    })

    render(<KillSwitchBanner />)

    await waitFor(() => {
      expect(screen.getByText(/system pausiert/i)).toBeInTheDocument()
    })
  })

  it("shows deactivate button when active", async () => {
    const mod = await import("@/lib/api")
    vi.mocked(mod.api.get).mockResolvedValue({
      active: true,
      reason: "drawdown",
      activated_at: "2026-03-06T10:00:00Z",
    })

    render(<KillSwitchBanner />)

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /deaktivieren/i }),
      ).toBeInTheDocument()
    })
  })

  it("shows banner on API error (fail-closed)", async () => {
    const mod = await import("@/lib/api")
    vi.mocked(mod.api.get).mockRejectedValue(new Error("Network error"))

    render(<KillSwitchBanner />)

    // Fail-closed: API error → assume active → banner shown
    await waitFor(() => {
      expect(screen.getByText(/system pausiert/i)).toBeInTheDocument()
    })
  })
})
