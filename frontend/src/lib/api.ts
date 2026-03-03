import { createClient } from "@/lib/supabase/client";
import { ApiError } from "./api-error";

class ApiClient {
  private get baseUrl(): string {
    const url = process.env.NEXT_PUBLIC_API_URL;
    if (!url) throw new Error("NEXT_PUBLIC_API_URL is not configured");
    return url;
  }

  async fetch<T>(path: string, options?: RequestInit): Promise<T> {
    const supabase = createClient();
    // getSession() reads the local token — fast, no network call.
    // The token is independently verified by the FastAPI backend.
    const {
      data: { session },
    } = await supabase.auth.getSession();

    const res = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(session?.access_token && {
          Authorization: `Bearer ${session.access_token}`,
        }),
        ...options?.headers,
      },
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({
        detail: `HTTP ${res.status}: ${res.statusText}`,
      }));
      throw new ApiError(res.status, body.detail ?? "Request failed");
    }

    return res.json();
  }

  get<T>(path: string) {
    return this.fetch<T>(path);
  }

  post<T>(path: string, body: unknown) {
    return this.fetch<T>(path, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  put<T>(path: string, body: unknown) {
    return this.fetch<T>(path, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  }

  delete<T>(path: string) {
    return this.fetch<T>(path, { method: "DELETE" });
  }
}

export const api = new ApiClient();
