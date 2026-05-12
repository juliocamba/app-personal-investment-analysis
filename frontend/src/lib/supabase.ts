/**
 * Supabase browser client — Phase 8 implementation.
 *
 * SECURITY MODEL:
 *  - Only VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are used here.
 *    The service-role key must never appear in frontend code.
 *  - The dashboard requires a Supabase Auth session before any data is shown.
 *  - `dashboard_watchlist_latest` is defined with `WITH (security_invoker = true)`
 *    (see sql/003_views_and_functions.sql).  RLS policies on the underlying tables
 *    are evaluated for the calling role, so the anon role cannot read the view
 *    even when presenting the public anon key.  SELECT is explicitly granted only
 *    to the `authenticated` role.
 *  - Provider API keys (FMP, SEC, etc.) must never appear in frontend code.
 */
import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

const _envMissing = !supabaseUrl || !supabaseAnonKey;

if (_envMissing) {
  // Surface clearly in browser console during development.
  // In Cloudflare Pages, env vars are injected at build time by the platform.
  console.error(
    "[supabase] VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY must be set. " +
      "Copy frontend/.env.example to frontend/.env and fill in the values.",
  );
}

// Guard against createClient throwing when env vars are absent (empty string
// fails Supabase's URL validation and crashes the entire app before any UI
// can render). A placeholder URL keeps the module loadable; auth will fail
// gracefully inside the UI instead of showing a blank page.
export const supabase = _envMissing
  ? createClient("https://placeholder.supabase.co", "placeholder-anon-key")
  : createClient(supabaseUrl!, supabaseAnonKey!);
