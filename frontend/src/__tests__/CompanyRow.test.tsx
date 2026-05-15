/**
 * Tests for CompanyRow readiness-aware rendering (Phase 10C.4).
 *
 * Verifies that rows with can_run_signal = false show a ReadinessBadge
 * instead of a SignalBadge, suppress probability columns, and display a
 * "Readiness notice" in the expanded detail panel.
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { CompanyRow } from "../components/CompanyRow";
import type { WatchlistRow } from "../types";

// Supabase is not imported by CompanyRow directly, so no mock is needed.

function makeRow(overrides: Partial<WatchlistRow> = {}): WatchlistRow {
  return {
    watchlist_membership_id: "wc-1",
    company_id: "id-1",
    ticker: "AAPL",
    name: "Apple Inc.",
    exchange: "NASDAQ",
    country: "US",
    currency: "USD",
    sector: null,
    industry: null,
    price_date: null,
    current_price: null,
    market_cap: null,
    roic: null,
    fcf_yield: null,
    net_debt_to_ebitda: null,
    news_sentiment_7d: null,
    final_quality_score: null,
    iv_p25: null,
    iv_p50: null,
    iv_p75: null,
    margin_of_safety_conservative: null,
    uncertainty_width: null,
    p_buy: null,
    p_buy_adjusted: null,
    p_sell: null,
    final_signal: null,
    red_flags: null,
    explanation: null,
    freshness_flag: null,
    readiness_status: null,
    provider_mix: null,
    readiness_reason_codes: null,
    can_run_valuation: null,
    can_run_signal: null,
    ...overrides,
  };
}

/** Render a CompanyRow inside a valid table structure. */
function renderRow(row: WatchlistRow) {
  return render(
    <table>
      <tbody>
        <CompanyRow row={row} />
      </tbody>
    </table>,
  );
}

const trackingRow = makeRow({
  ticker: "ASML",
  name: "ASML Holding",
  current_price: 1584.51,
  final_signal: "hold",
  readiness_status: "tracking_only",
  provider_mix: "price_only",
  readiness_reason_codes: ["provider_limited"],
  can_run_valuation: false,
  can_run_signal: false,
});

const analysisReadyRow = makeRow({
  ticker: "AAPL",
  name: "Apple Inc.",
  current_price: 195.0,
  final_signal: "BUY",
  explanation: "Strong fundamentals with attractive valuation.",
  readiness_status: "analysis_ready",
  can_run_valuation: true,
  can_run_signal: true,
  p_buy_adjusted: 0.72,
  p_sell: 0.12,
});

// ---------------------------------------------------------------------------
// tracking_only row — compact view
// ---------------------------------------------------------------------------

describe("CompanyRow — tracking_only compact view", () => {
  it("shows ReadinessBadge instead of SignalBadge when can_run_signal = false", () => {
    renderRow(trackingRow);
    expect(screen.getByTestId("readiness-badge")).toBeInTheDocument();
    expect(screen.queryByTestId("signal-badge")).not.toBeInTheDocument();
  });

  it("ReadinessBadge displays 'Tracking only' label", () => {
    renderRow(trackingRow);
    expect(screen.getByTestId("readiness-badge")).toHaveTextContent("Tracking only");
  });

  it("suppresses p_buy_adjusted value when can_run_signal = false", () => {
    // Set a non-null value to confirm it is actively suppressed
    renderRow(makeRow({ ...trackingRow, p_buy_adjusted: 0.72 }));
    expect(screen.queryByText("72.0%")).not.toBeInTheDocument();
  });

  it("suppresses p_sell value when can_run_signal = false", () => {
    renderRow(makeRow({ ...trackingRow, p_sell: 0.35 }));
    expect(screen.queryByText("35.0%")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// tracking_only row — expanded detail panel
// ---------------------------------------------------------------------------

describe("CompanyRow — tracking_only expanded panel", () => {
  it("shows 'Readiness notice' heading in the expanded panel", () => {
    renderRow(trackingRow);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Readiness notice")).toBeInTheDocument();
  });

  it("shows provider coverage in the expanded panel", () => {
    renderRow(trackingRow);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("price_only")).toBeInTheDocument();
  });

  it("shows human-friendly reason code label in the expanded panel", () => {
    renderRow(trackingRow);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Provider coverage limited")).toBeInTheDocument();
  });

  it("does not show 'Signal explanation' section for tracking_only rows", () => {
    renderRow(makeRow({ ...trackingRow, explanation: "Some explanation text" }));
    fireEvent.click(screen.getByRole("button"));
    expect(screen.queryByText("Signal explanation")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// analysis_ready row
// ---------------------------------------------------------------------------

describe("CompanyRow — analysis_ready row", () => {
  it("shows SignalBadge when can_run_signal = true", () => {
    renderRow(analysisReadyRow);
    expect(screen.getByTestId("signal-badge")).toBeInTheDocument();
    expect(screen.queryByTestId("readiness-badge")).not.toBeInTheDocument();
  });

  it("shows formatted p_buy_adjusted when can_run_signal = true", () => {
    renderRow(analysisReadyRow);
    expect(screen.getByText("72.0%")).toBeInTheDocument();
  });

  it("shows 'Signal explanation' heading in expanded panel", () => {
    renderRow(analysisReadyRow);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Signal explanation")).toBeInTheDocument();
    expect(
      screen.getByText("Strong fundamentals with attractive valuation."),
    ).toBeInTheDocument();
  });

  it("does not show 'Readiness notice' for analysis_ready rows", () => {
    renderRow(analysisReadyRow);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.queryByText("Readiness notice")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Null / legacy readiness fields — fallback behaviour
// ---------------------------------------------------------------------------

describe("CompanyRow — null readiness fields fallback", () => {
  it("shows SignalBadge normally when all readiness fields are null", () => {
    renderRow(makeRow({ ticker: "GOOG", final_signal: "HOLD" }));
    expect(screen.getByTestId("signal-badge")).toBeInTheDocument();
  });

  it("does not crash when can_run_signal is null", () => {
    renderRow(makeRow({ ticker: "GOOG", can_run_signal: null }));
    expect(screen.getByText("GOOG")).toBeInTheDocument();
  });

  it("ReadinessBadge shows 'Unknown' when readiness_status is null but can_run_signal = false", () => {
    renderRow(makeRow({ can_run_signal: false, readiness_status: null }));
    expect(screen.getByTestId("readiness-badge")).toHaveTextContent("Unknown");
  });
});
