import React, { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./lib/supabase";
import { Disclaimer } from "./components/Disclaimer";
import { LoginPage } from "./pages/LoginPage";
import { WatchlistPage } from "./pages/WatchlistPage";
import { AlertsPage } from "./pages/AlertsPage";
import { PositionsPage } from "./pages/PositionsPage";

type Page = "watchlist" | "positions" | "alerts";

/**
 * Root application component.
 *
 * Auth flow:
 *  1. On mount, retrieve the existing Supabase session (if any).
 *  2. Subscribe to auth state changes — the subscriber fires immediately
 *     with the current state, then on every sign-in / sign-out event.
 *  3. If there is no session, render <LoginPage />.
 *  4. If there is a session, render the main dashboard.
 */
export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [page, setPage] = useState<Page>("watchlist");

  useEffect(() => {
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
      setAuthLoading(false);
    });

    // Trigger an immediate session check.
    supabase.auth.getSession().then(({ data: { session: s } }) => {
      setSession(s);
      setAuthLoading(false);
    });

    return () => subscription.unsubscribe();
  }, []);

  if (authLoading) {
    return (
      <div className="page-state" aria-live="polite" aria-busy="true">
        <div className="spinner" aria-label="Checking authentication…" />
      </div>
    );
  }

  if (!session) {
    return <LoginPage />;
  }

  return (
    <div className="app">
      <Disclaimer />

      {/* ── Navigation ───────────────────────────────────── */}
      <nav className="nav" aria-label="Main navigation">
        <span className="nav__brand">Investment Dashboard</span>
        <div className="nav__links">
          <button
            className={`nav__link ${page === "watchlist" ? "nav__link--active" : ""}`}
            onClick={() => setPage("watchlist")}
            aria-current={page === "watchlist" ? "page" : undefined}
          >
            Watchlist
          </button>
          <button
            className={`nav__link ${page === "positions" ? "nav__link--active" : ""}`}
            onClick={() => setPage("positions")}
            aria-current={page === "positions" ? "page" : undefined}
          >
            Positions
          </button>
          <button
            className={`nav__link ${page === "alerts" ? "nav__link--active" : ""}`}
            onClick={() => setPage("alerts")}
            aria-current={page === "alerts" ? "page" : undefined}
          >
            Alerts
          </button>
        </div>
        <div className="nav__user">
          <span title={session.user.email}>{session.user.email}</span>
          <button
            className="nav__signout"
            onClick={() => supabase.auth.signOut()}
            aria-label="Sign out"
          >
            Sign out
          </button>
        </div>
      </nav>

      {/* ── Main content ─────────────────────────────────── */}
      <main className="main-content" id="main">
        {page === "watchlist" ? (
          <WatchlistPage />
        ) : page === "positions" ? (
          <PositionsPage />
        ) : (
          <AlertsPage />
        )}
      </main>
    </div>
  );
}
