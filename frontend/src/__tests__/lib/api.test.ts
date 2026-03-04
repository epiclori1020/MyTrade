import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError } from "@/lib/api-error"

vi.mock("@/lib/supabase/client", () => ({
  createClient: vi.fn(() => ({
    auth: {
      getSession: vi.fn(() =>
        Promise.resolve({
          data: { session: { access_token: "test-token" } },
          error: null,
        }),
      ),
    },
  })),
}))

vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000")

describe("ApiClient", () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockFetch = vi.fn()
    vi.stubGlobal("fetch", mockFetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it("attaches Bearer token from Supabase session", async () => {
    const { api } = await import("@/lib/api")

    mockFetch.mockResolvedValueOnce({
      ok: true,
      text: () => Promise.resolve(JSON.stringify({ data: "ok" })),
    })

    await api.get("/api/health")

    expect(mockFetch).toHaveBeenCalledOnce()
    const [, options] = mockFetch.mock.calls[0] as [string, RequestInit]
    expect((options.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer test-token",
    )
  })

  it("throws ApiError on non-OK response (400)", async () => {
    const { api } = await import("@/lib/api")

    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: () => Promise.resolve({ detail: "Invalid ticker" }),
    })

    await expect(api.get("/api/policy/pre-check/BAD")).rejects.toMatchObject({
      name: "ApiError",
      status: 400,
      detail: "Invalid ticker",
    })
  })

  it("throws ApiError on 500 response", async () => {
    const { api } = await import("@/lib/api")

    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.resolve({ detail: "Server error" }),
    })

    const err = await api.post("/api/analyze/AAPL", {}).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(500)
  })

  it("handles missing session gracefully (no Authorization header)", async () => {
    const { createClient } = await import("@/lib/supabase/client")
    vi.mocked(createClient).mockReturnValueOnce({
      auth: {
        getSession: vi.fn(() =>
          Promise.resolve({
            data: { session: null },
            error: null,
          }),
        ),
      },
    } as ReturnType<typeof createClient>)

    const { api } = await import("@/lib/api")

    mockFetch.mockResolvedValueOnce({
      ok: true,
      text: () => Promise.resolve(JSON.stringify({ data: "ok" })),
    })

    await api.get("/api/health")

    const [, options] = mockFetch.mock.calls[0] as [string, RequestInit]
    expect(
      (options.headers as Record<string, string>)["Authorization"],
    ).toBeUndefined()
  })
})
