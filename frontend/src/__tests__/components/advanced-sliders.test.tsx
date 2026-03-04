import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { AdvancedSliders } from "@/components/settings/advanced-sliders"
import type { PolicyMode, PresetId } from "@/lib/types"

const DEFAULT_PROPS = {
  mode: "PRESET" as PolicyMode,
  preset: "balanced" as PresetId,
  overrides: {},
  onModeChange: vi.fn(),
  onOverrideChange: vi.fn(),
}

describe("AdvancedSliders", () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("shows switch toggle for Advanced mode", () => {
    render(<AdvancedSliders {...DEFAULT_PROPS} />)

    const toggle = screen.getByRole("switch")
    expect(toggle).toBeInTheDocument()
    expect(screen.getByText("Erweiterte Einstellungen")).toBeInTheDocument()
  })

  it("checkbox is interactive and starts unchecked", async () => {
    const user = userEvent.setup()

    render(
      <AdvancedSliders
        {...DEFAULT_PROPS}
        mode="ADVANCED"
        onModeChange={vi.fn()}
      />,
    )

    const checkbox = screen.getByRole("checkbox")
    expect(checkbox).toBeInTheDocument()
    expect(checkbox).not.toBeChecked()

    await user.click(checkbox)
    expect(checkbox).toBeChecked()
  })

  it("sliders are hidden when not in ADVANCED mode", () => {
    render(<AdvancedSliders {...DEFAULT_PROPS} mode="PRESET" />)

    // In PRESET mode: no card content, no checkbox, no sliders
    expect(screen.queryAllByRole("slider")).toHaveLength(0)
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument()
  })

  it("sliders are visible when in ADVANCED mode and checkbox is confirmed", async () => {
    const user = userEvent.setup()

    render(
      <AdvancedSliders
        {...DEFAULT_PROPS}
        mode="ADVANCED"
        onModeChange={vi.fn()}
      />,
    )

    // Before confirmation: checkbox exists but no sliders yet
    const checkbox = screen.getByRole("checkbox")
    expect(screen.queryAllByRole("slider")).toHaveLength(0)

    // Confirm the risk acknowledgement
    await user.click(checkbox)

    // Now sliders should be visible (one per SLIDER_CONFIG entry = 9 sliders)
    const sliders = screen.getAllByRole("slider")
    expect(sliders.length).toBeGreaterThan(0)

    expect(screen.getByText("Satellite-Anteil")).toBeInTheDocument()
    expect(screen.getByText("Max Drawdown (Kill-Switch)")).toBeInTheDocument()
  })
})
