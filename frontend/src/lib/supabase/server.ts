import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

/**
 * Server-side Supabase client for Server Components and Route Handlers.
 *
 * IMPORTANT: cookies() is async in Next.js 15+. This function must be awaited:
 *   const supabase = await createClient();
 *
 * Uses the anon key — RLS enforces row-level access.
 * Never expose service_role key to the frontend.
 */
export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            );
          } catch {
            // setAll is called from Server Components where cookies are read-only.
            // The middleware handles session refresh, so this is safe to ignore.
          }
        },
      },
    }
  );
}
