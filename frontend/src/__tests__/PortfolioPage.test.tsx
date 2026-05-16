import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  fetchPortfolioPositions: vi.fn(),
  fetchPortfolioPositionsFxEur: vi.fn(),
  fetchPortfolioSummary: vi.fn(),
  fetchPortfolioSummaryFxEur: vi.fn(),
}));

import { PortfolioPage } from "../pages/PortfolioPage";
import {
  fetchPortfolioPositions,
  fetchPortfolioPositionsFxEur,
  fetchPortfolioSummary,
  fetchPortfolioSummaryFxEur,
} from "../lib/api";
import type {
  PortfolioPositionFxEurRow,
  PortfolioPositionRow,
  PortfolioSummaryFxEurRow,
  PortfolioSummaryRow,
} from "../types";

function makeSummary(
  overrides: Partial<PortfolioSummaryRow> = {},
): PortfolioSummaryRow {
  return {
    active_position_count: 2,
    closed_position_count: 1,
    active_positions_with_price: 1,
    active_positions_missing_price: 1,
    active_positions_currency_mismatch: 0,
    computable_total_cost_basis: 1500,
    computable_total_market_value: 1800,
    computable_total_unrealized_gain_loss: 300,
    computable_total_unrealized_return_pct: 0.2,
    open_review_alert_count: 1,
    critical_data_quality_count: 1,
    positions_by_signal: [{ signal: "buy", count: 1 }, { signal: "hold", count: 1 }],
    positions_by_thesis_confidence: [{ confidence_level: "high", count: 1 }],
    company_concentration: [
      { ticker: "AAPL", name: "Apple Inc.", current_value: 1800, weight_pct: 1 },
    ],
    sector_exposure: [
      { sector: "Technology", current_value: 1800, weight_pct: 1 },
    ],
    geography_exposure: [
      { country: "US", current_value: 1800, weight_pct: 1 },
    ],
    ...overrides,
  };
}

function makeFxSummary(
  overrides: Partial<PortfolioSummaryFxEurRow> = {},
): PortfolioSummaryFxEurRow {
  return {
    normalized_total_cost_basis_eur: 1400,
    normalized_total_market_value_eur: 1680,
    normalized_total_unrealized_gain_loss_eur: 280,
    normalized_total_unrealized_return_pct: 0.2,
    positions_missing_fx_rate: 0,
    positions_fx_normalized_count: 1,
    ...overrides,
  };
}

function makePosition(
  overrides: Partial<PortfolioPositionRow> = {},
): PortfolioPositionRow {
  return {
    id: "pos-1",
    user_id: "user-1",
    company_id: "company-1",
    ticker: "AAPL",
    name: "Apple Inc.",
    sector: "Technology",
    country: "US",
    entry_date: "2026-05-01",
    quantity: 10,
    average_entry_price: 150,
    currency: "USD",
    fees: 0,
    notes: null,
    status: "active",
    closed_at: null,
    price_date: "2026-05-15",
    current_price: 180,
    price_currency: "USD",
    cost_basis: 1500,
    current_value: 1800,
    unrealized_gain_loss: 300,
    unrealized_return_pct: 0.2,
    current_signal: "buy",
    current_readiness_status: "analysis_ready",
    current_data_quality_status: "healthy",
    current_quality_score: 82,
    current_valuation_low: 160,
    current_valuation_mid: 200,
    current_valuation_high: 240,
    current_margin_of_safety: 0.1,
    current_uncertainty_category: "moderate",
    thesis_confidence_level: "high",
    open_review_alert_count: 1,
    highest_open_review_alert_severity: "warning",
    missing_current_price: false,
    currency_mismatch: false,
    value_computable: true,
    position_weight_pct: 1,
    ...overrides,
  };
}

function makeFxPosition(
  overrides: Partial<PortfolioPositionFxEurRow> = {},
): PortfolioPositionFxEurRow {
  return {
    ...makePosition(),
    normalized_cost_basis_eur: 1400,
    normalized_current_value_eur: 1680,
    normalized_unrealized_gain_loss_eur: 280,
    normalized_position_weight_pct: 1,
    ...overrides,
  };
}

describe("PortfolioPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchPortfolioSummary).mockResolvedValue(makeSummary());
    vi.mocked(fetchPortfolioPositions).mockResolvedValue([makePosition()]);
    vi.mocked(fetchPortfolioSummaryFxEur).mockResolvedValue(makeFxSummary());
    vi.mocked(fetchPortfolioPositionsFxEur).mockResolvedValue([makeFxPosition()]);
  });

  it("renders summary cards and exposure sections", async () => {
    render(<PortfolioPage />);

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /Portfolio/i })).toBeInTheDocument(),
    );
    expect(screen.getAllByText("$1,800.00")).toHaveLength(2);
    expect(screen.getByText("20.0%")).toBeInTheDocument();
    expect(screen.getByText(/Positions by signal/i)).toBeInTheDocument();
    expect(screen.getByText(/AAPL 100.0%/i)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /Portfolio positions/i })).toBeInTheDocument();
  });

  it("renders coverage warnings for baseline and fx-normalized sections", async () => {
    vi.mocked(fetchPortfolioSummary).mockResolvedValue(
      makeSummary({
        active_positions_missing_price: 1,
        active_positions_currency_mismatch: 1,
      }),
    );
    vi.mocked(fetchPortfolioSummaryFxEur).mockResolvedValue(
      makeFxSummary({
        positions_missing_fx_rate: 1,
        positions_fx_normalized_count: 1,
      }),
    );

    render(<PortfolioPage />);

    await waitFor(() => expect(screen.getByText(/Coverage note/i)).toBeInTheDocument());
    expect(
      screen.getByText(/Portfolio totals exclude positions with missing current prices or currency mismatches/i),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Show EUR estimate/i }));

    expect(screen.getByText(/FX-normalized estimate \(EUR\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Uses stored ECB daily FX rates matched by exact price date only/i)).toBeInTheDocument();
    expect(screen.getByText(/FX coverage note/i)).toBeInTheDocument();
    expect(
      screen.getByText(/FX-normalized totals exclude rows without an exact-date stored ECB FX rate/i),
    ).toBeInTheDocument();
  });

  it("keeps original values visible when fx estimate is shown", async () => {
    render(<PortfolioPage />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Show EUR estimate/i })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /Show EUR estimate/i }));

    expect(screen.getAllByText("$1,800.00")).toHaveLength(2);
    expect(screen.getByText(/Normalized value \(EUR\)/i)).toBeInTheDocument();
    expect(screen.getAllByText("€1,680.00")).toHaveLength(2);
  });

  it("shows an empty state when no positions exist yet", async () => {
    vi.mocked(fetchPortfolioSummary).mockResolvedValue(
      makeSummary({
        active_position_count: 0,
        closed_position_count: 0,
        active_positions_with_price: 0,
        active_positions_missing_price: 0,
        active_positions_currency_mismatch: 0,
        computable_total_cost_basis: 0,
        computable_total_market_value: 0,
        computable_total_unrealized_gain_loss: 0,
        computable_total_unrealized_return_pct: null,
        open_review_alert_count: 0,
        critical_data_quality_count: 0,
        positions_by_signal: [],
        positions_by_thesis_confidence: [],
        company_concentration: [],
        sector_exposure: [],
        geography_exposure: [],
      }),
    );
    vi.mocked(fetchPortfolioPositions).mockResolvedValue([]);
    vi.mocked(fetchPortfolioSummaryFxEur).mockResolvedValue(
      makeFxSummary({
        normalized_total_cost_basis_eur: 0,
        normalized_total_market_value_eur: 0,
        normalized_total_unrealized_gain_loss_eur: 0,
        normalized_total_unrealized_return_pct: null,
        positions_missing_fx_rate: 0,
        positions_fx_normalized_count: 0,
      }),
    );
    vi.mocked(fetchPortfolioPositionsFxEur).mockResolvedValue([]);

    render(<PortfolioPage />);

    await waitFor(() =>
      expect(screen.getByText(/No portfolio positions yet/i)).toBeInTheDocument(),
    );
  });
});
