import { createClient } from "@/lib/supabase/server";
import { NextRequest, NextResponse } from "next/server";

/**
 * PKCE Auth Callback — exchanges the one-time code for a session.
 *
 * Supabase redirects here after email confirmation, OAuth sign-in, or
 * magic-link clicks with ?code=<PKCE_CODE>.
 *
 * Flow:
 *   1. Read `code` from search params.
 *   2. Exchange for a session (server-side, secure).
 *   3. Redirect to /dashboard on success, /login?error=auth on failure.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl;
  const code = searchParams.get("code");

  if (!code) {
    // No code present — likely a direct visit to this URL.
    return NextResponse.redirect(`${origin}/login?error=auth`);
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    console.error("[auth/callback] exchangeCodeForSession error:", error.message);
    return NextResponse.redirect(`${origin}/login?error=auth`);
  }

  // Session established. Redirect to the intended destination or dashboard.
  const next = searchParams.get("next") ?? "/dashboard";

  // Validate the redirect target is a relative path (no open-redirect).
  const safeNext = next.startsWith("/") ? next : "/dashboard";

  return NextResponse.redirect(`${origin}${safeNext}`);
}
