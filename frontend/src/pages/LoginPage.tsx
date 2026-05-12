import React, { useState } from "react";
import { supabase } from "../lib/supabase";
import { Disclaimer } from "../components/Disclaimer";

/**
 * Sign-in form backed by Supabase Auth (email + password).
 *
 * The dashboard requires authentication because:
 *  - alert_history RLS restricts rows to the authenticated user's own alerts.
 *  - For the watchlist view, authentication acts as the primary access gate
 *    even though the underlying PostgreSQL view uses security-definer defaults.
 *
 * After a successful sign-in, App.tsx detects the new session via
 * supabase.auth.onAuthStateChange and unmounts this page automatically.
 */
export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !password) return;

    setLoading(true);
    setError(null);

    const { error: authError } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });

    if (authError) {
      setError(authError.message);
    }
    // On success, App.tsx's onAuthStateChange listener updates the session.
    setLoading(false);
  }

  return (
    <div className="login-page">
      <Disclaimer />
      <div className="login-card">
        <h1 className="login-card__title">Investment Dashboard</h1>
        <p className="login-card__subtitle">Sign in to view your private research data.</p>

        <form className="login-form" onSubmit={handleSubmit} noValidate>
          <div className="form-group">
            <label className="form-label" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              className="form-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              required
              disabled={loading}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              className="form-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
              disabled={loading}
            />
          </div>

          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}

          <button
            type="submit"
            className="btn btn--primary btn--full"
            disabled={loading || !email.trim() || !password}
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="login-card__note">
          This dashboard requires a Supabase user account. Contact the system
          owner to create one.
        </p>
      </div>
    </div>
  );
}
