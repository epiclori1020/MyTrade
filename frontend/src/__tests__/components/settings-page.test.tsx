import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// --- Child component mocks ---

vi.mock("@/components/settings/preset-cards", () => ({
  PresetCards: () => <div data-testid="preset-cards" />,
}))

vi.mock("@/components/settings/comparison-table", () => ({
  ComparisonTable: () => <div data-testid="comparison-table" />,
}))

vi.mock("@/components/settings/advanced-sliders", () => ({
  AdvancedSliders: () => <div data-testid="advanced-sliders" />,
}))

vi.mock("@/components/settings/cooldown-banner", () => ({
  CooldownBanner: () => <div data-testid="cooldown-banner" />,
}))

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), put: vi.fn() },
}))

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

// --- Imports after mocks are defined ---

import SettingsPage from "@/app/(dashboard)/settings/page"

describe("SettingsPage", () => {
  let mockGet: ReturnType<typeof vi.fn>

  beforeEach(async () => {
    const mod = await import("@/lib/api")
    mockGet = vi.mocked(mod.api.get)
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("loads settings and presets successfully", async () => {
    mockGet
      .mockResolvedValueOnce({
        policy_mode: "PRESET",
        preset_id: "balanced",
        policy_overrides: {},
        cooldown_until: null,
      })
      .mockResolvedValueOnce({
        presets: { beginner: {}, balanced: {}, active: {} },
        constraints: {},
      })

    render(<SettingsPage />)

    await waitFor(() => {
      expect(screen.getByTestId("preset-cards")).toBeInTheDocument()
    })

    const { toast } = await import("sonner")
    expect(toast.warning).not.toHaveBeenCalled()
  })

  it("shows warning toast when presets fetch fails", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes("/presets")) return Promise.reject(new Error("Network error"))
      return Promise.resolve({
        policy_mode: "PRESET",
        preset_id: "balanced",
        policy_overrides: {},
        cooldown_until: null,
      })
    })

    render(<SettingsPage />)

    await waitFor(() => {
      expect(screen.getByTestId("preset-cards")).toBeInTheDocument()
    })

    const { toast } = await import("sonner")
    expect(toast.warning).toHaveBeenCalledWith(
      expect.stringContaining("Preset-Daten"),
    )
  })
})
