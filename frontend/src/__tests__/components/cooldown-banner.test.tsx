import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { CooldownBanner } from "@/components/settings/cooldown-banner"
import type { PresetId } from "@/lib/types"

function futureDate(offsetMs: number): string {
  return new Date(Date.now() + offsetMs).toISOString()
}

function pastDate(offsetMs: number): string {
  return new Date(Date.now() - offsetMs).toISOString()
}

describe("CooldownBanner", () => {
  it("shows countdown when cooldown is in the future", () => {
    // 2 hours from now
    const cooldownUntil = futureDate(2 * 60 * 60 * 1000)

    render(<CooldownBanner cooldownUntil={cooldownUntil} presetId={"active" as PresetId} />)

    // Should show the preset label "Aktiv" (from PRESET_META)
    expect(screen.getByText("Aktiv")).toBeInTheDocument()

    // Should show the countdown text
    expect(screen.getByText(/wechsel zu/i)).toBeInTheDocument()
    expect(screen.getByText(/aktiv ab/i)).toBeInTheDocument()

    // Should show remaining time  (2h or 1h something)
    expect(screen.getByText(/in \d+h/)).toBeInTheDocument()
  })

  it("returns null when cooldown has passed", () => {
    // 1 hour in the past
    const cooldownUntil = pastDate(60 * 60 * 1000)

    const { container } = render(
      <CooldownBanner cooldownUntil={cooldownUntil} presetId={"balanced" as PresetId} />,
    )

    // Component should render nothing
    expect(container.firstChild).toBeNull()
  })

  it("shows correct preset name in banner", () => {
    const cooldownUntil = futureDate(30 * 60 * 1000) // 30 minutes from now

    const { container } = render(
      <CooldownBanner cooldownUntil={cooldownUntil} presetId={"beginner" as PresetId} />,
    )

    // "Einsteiger" is the label from PRESET_META for "beginner"
    expect(screen.getByText("Einsteiger")).toBeInTheDocument()
    // Banner text contains "Wechsel zu ... aktiv ab"
    const paragraph = container.querySelector("p")
    expect(paragraph).not.toBeNull()
    expect(paragraph!.textContent).toMatch(/wechsel zu/i)
    expect(paragraph!.textContent).toMatch(/aktiv ab/i)
  })
})
