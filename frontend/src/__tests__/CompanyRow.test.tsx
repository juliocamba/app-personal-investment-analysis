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
    mos_basis: null,
    scenario_count: null,
    uncertainty_category: null,
    distribution_collapsed: null,
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

  it("suppresses p_buy (raw) in the expanded detail panel when can_run_signal = false", () => {
    renderRow(makeRow({ ...trackingRow, p_buy: 0.55 }));
    fireEvent.click(screen.getByRole("button"));
    expect(screen.queryByText("55.0%")).not.toBeInTheDocument();
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

// ---------------------------------------------------------------------------
// Valuation diagnostics section — Phase 11A.5
// ---------------------------------------------------------------------------

describe("CompanyRow — valuation diagnostics section", () => {
  const withDiagnostics = makeRow({
    ticker: "ORCL",
    name: "Oracle Corp.",
    readiness_status: "analysis_ready",
    can_run_valuation: true,
    can_run_signal: true,
    mos_basis: "iv_p10",
    scenario_count: 3,
    uncertainty_category: "moderate",
    distribution_collapsed: false,
  });

  it("shows 'Valuation diagnostics' heading for analysis_ready rows", () => {
    renderRow(withDiagnostics);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Valuation diagnostics")).toBeInTheDocument();
  });

  it("renders MoS basis field", () => {
    renderRow(withDiagnostics);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("MoS basis")).toBeInTheDocument();
    expect(screen.getByText("iv_p10")).toBeInTheDocument();
  });

  it("renders DCF scenarios as N/3 format", () => {
    renderRow(withDiagnostics);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("DCF scenarios")).toBeInTheDocument();
    expect(screen.getByText("3/3")).toBeInTheDocument();
  });

  it("renders uncertainty category with capitalised first letter", () => {
    renderRow(withDiagnostics);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Valuation uncertainty")).toBeInTheDocument();
    expect(screen.getByText("Moderate")).toBeInTheDocument();
  });

  it("does not show distribution-collapsed warning when false", () => {
    renderRow(withDiagnostics);
    fireEvent.click(screen.getByRole("button"));
    expect(
      screen.queryByTestId("distribution-collapsed-warning"),
    ).not.toBeInTheDocument();
  });

  it("shows distribution-collapsed warning when distribution_collapsed is true", () => {
    renderRow(makeRow({ ...withDiagnostics, distribution_collapsed: true }));
    fireEvent.click(screen.getByRole("button"));
    expect(
      screen.getByTestId("distribution-collapsed-warning"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Valuation distribution collapsed — limited scenario/method diversity.",
      ),
    ).toBeInTheDocument();
  });

  it("does not show distribution-collapsed warning when null", () => {
    renderRow(makeRow({ ...withDiagnostics, distribution_collapsed: null }));
    fireEvent.click(screen.getByRole("button"));
    expect(
      screen.queryByTestId("distribution-collapsed-warning"),
    ).not.toBeInTheDocument();
  });

  it("shows em-dash for null diagnostic fields", () => {
    renderRow(
      makeRow({
        readiness_status: "analysis_ready",
        can_run_valuation: true,
        can_run_signal: true,
        mos_basis: null,
        scenario_count: null,
        uncertainty_category: null,
      }),
    );
    fireEvent.click(screen.getByRole("button"));
    // Three em-dashes are rendered for the three null fields
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(3);
  });

  it("hides Valuation diagnostics section for tracking_only rows", () => {
    renderRow(
      makeRow({
        ...trackingRow,
        mos_basis: "iv_p10",
        scenario_count: 3,
        uncertainty_category: "low",
      }),
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.queryByText("Valuation diagnostics")).not.toBeInTheDocument();
  });

  it("hides Valuation diagnostics section when can_run_valuation is false", () => {
    renderRow(
      makeRow({
        can_run_valuation: false,
        can_run_signal: true,
        mos_basis: "iv_p10",
        scenario_count: 2,
      }),
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.queryByText("Valuation diagnostics")).not.toBeInTheDocument();
  });

  it("hides Valuation diagnostics when can_run_signal=false even if can_run_valuation=true", () => {
    // Inconsistent row: tracking_only signal but valuation capability reported as true.
    // Diagnostics must stay hidden because the readiness notice path takes over.
    renderRow(
      makeRow({
        can_run_signal: false,
        can_run_valuation: true,
        readiness_status: "provider_limited",
        mos_basis: "iv_p10",
        scenario_count: 3,
        uncertainty_category: "low",
      }),
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Readiness notice")).toBeInTheDocument();
    expect(screen.queryByText("Valuation diagnostics")).not.toBeInTheDocument();
  });

  it("shows Valuation diagnostics section when can_run_valuation is null (legacy rows)", () => {
    renderRow(
      makeRow({
        can_run_valuation: null,
        can_run_signal: null,
        mos_basis: "iv_p10",
        scenario_count: 1,
        uncertainty_category: "high",
      }),
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Valuation diagnostics")).toBeInTheDocument();
  });
});

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
