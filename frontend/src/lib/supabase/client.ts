import { createBrowserClient } from "@supabase/ssr";

/**
 * Browser-side Supabase client.
 * Safe to call in Client Components — uses anon key only.
 * Call once per render; memoization is handled internally by @supabase/ssr.
 */
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
}
