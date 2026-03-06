import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import LoginPage from "@/app/(auth)/login/page"

const mockPush = vi.fn()
const mockRefresh = vi.fn()
const mockSignIn = vi.fn().mockResolvedValue({ error: null })

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, refresh: mockRefresh }),
}))

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      signInWithPassword: mockSignIn,
    },
  }),
}))

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode
    href: string
  }) => <a href={href}>{children}</a>,
}))

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it("renders login form elements", () => {
    render(<LoginPage />)

    expect(screen.getByText("Anmelden", { selector: "[data-slot='card-title']" })).toBeInTheDocument()
    expect(screen.getByLabelText("E-Mail")).toBeInTheDocument()
    expect(screen.getByLabelText("Passwort")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Anmelden" }),
    ).toBeInTheDocument()
  })

  it("renders signup link", () => {
    render(<LoginPage />)

    const link = screen.getByRole("link", { name: "Registrieren" })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute("href", "/signup")
  })

  it("has required attributes on inputs", () => {
    render(<LoginPage />)

    const emailInput = screen.getByLabelText("E-Mail")
    expect(emailInput).toHaveAttribute("type", "email")

    const passwordInput = screen.getByLabelText("Passwort")
    expect(passwordInput).toHaveAttribute("type", "password")
  })

  it("shows Anmelden text on submit button initially", () => {
    render(<LoginPage />)

    const button = screen.getByRole("button", { name: "Anmelden" })
    expect(button).toHaveTextContent("Anmelden")
    expect(button).not.toBeDisabled()
  })

  it("calls signInWithPassword and navigates on success", async () => {
    const user = userEvent.setup()
    render(<LoginPage />)

    await user.type(screen.getByLabelText("E-Mail"), "test@example.com")
    await user.type(screen.getByLabelText("Passwort"), "password123")
    await user.click(screen.getByRole("button", { name: "Anmelden" }))

    expect(mockSignIn).toHaveBeenCalledWith({
      email: "test@example.com",
      password: "password123",
    })
    expect(mockPush).toHaveBeenCalledWith("/dashboard")
    expect(mockRefresh).toHaveBeenCalled()
  })

  it("shows error toast on auth failure", async () => {
    mockSignIn.mockResolvedValueOnce({
      error: { message: "Invalid credentials" },
    })

    const user = userEvent.setup()
    render(<LoginPage />)

    await user.type(screen.getByLabelText("E-Mail"), "bad@example.com")
    await user.type(screen.getByLabelText("Passwort"), "wrong")
    await user.click(screen.getByRole("button", { name: "Anmelden" }))

    const { toast } = await import("sonner")
    expect(toast.error).toHaveBeenCalledWith("Invalid credentials")
    expect(mockPush).not.toHaveBeenCalled()
  })
})
