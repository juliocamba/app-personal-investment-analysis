import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  fetchSignalBacktestByDataQuality: vi.fn(),
  fetchSignalBacktestByReadiness: vi.fn(),
  fetchSignalBacktestBySector: vi.fn(),
  fetchSignalBacktestCoverageRows: vi.fn(),
  fetchSignalBacktestInterpretationSummary: vi.fn(),
  fetchSignalBacktestSummaryByBucket: vi.fn(),
  fetchSignalBacktestSummaryByHorizon: vi.fn(),
  fetchSignalBacktestStability: vi.fn(),
}));

import { SignalValidationPage } from "../pages/SignalValidationPage";
import {
  fetchSignalBacktestByDataQuality,
  fetchSignalBacktestByReadiness,
  fetchSignalBacktestBySector,
  fetchSignalBacktestCoverageRows,
  fetchSignalBacktestInterpretationSummary,
  fetchSignalBacktestSummaryByBucket,
  fetchSignalBacktestSummaryByHorizon,
  fetchSignalBacktestStability,
} from "../lib/api";
import type {
  SignalBacktestBucketSummaryRow,
  SignalBacktestCoverageRow,
  SignalBacktestHorizonSummaryRow,
  SignalBacktestInterpretationSummaryRow,
  SignalBacktestSegmentSummaryRow,
  SignalBacktestStabilityRow,
} from "../types";

function makeBucketRow(
  overrides: Partial<SignalBacktestBucketSummaryRow> = {},
): SignalBacktestBucketSummaryRow {
  return {
    final_signal: "buy",
    horizon_days: 30,
    observation_count: 12,
    covered_observation_count: 10,
    average_return: 0.08,
    median_return: 0.05,
    hit_rate: 0.6,
    coverage_pct: 10 / 12,
    ...overrides,
  };
}

function makeHorizonRow(
  overrides: Partial<SignalBacktestHorizonSummaryRow> = {},
): SignalBacktestHorizonSummaryRow {
  return {
    horizon_days: 30,
    observation_count: 40,
    covered_observation_count: 32,
    average_return: 0.06,
    median_return: 0.04,
    hit_rate: 0.55,
    coverage_pct: 0.8,
    ...overrides,
  };
}

function makeSegmentRow(
  overrides: Partial<SignalBacktestSegmentSummaryRow> = {},
): SignalBacktestSegmentSummaryRow {
  return {
    final_signal: "buy",
    horizon_days: 30,
    observation_count: 8,
    covered_observation_count: 6,
    average_return: 0.04,
    median_return: 0.03,
    hit_rate: 0.5,
    coverage_pct: 0.75,
    readiness_status_at_signal: "unknown",
    data_quality_status_at_signal: "warning",
    sector_at_signal: "Technology",
    ...overrides,
  };
}

function makeStabilityRow(
  overrides: Partial<SignalBacktestStabilityRow> = {},
): SignalBacktestStabilityRow {
  return {
    signal_bucket: "buy",
    observation_count: 12,
    transition_count: 10,
    flip_count: 4,
    stable_transition_count: 6,
    flip_rate: 0.4,
    stability_pct: 0.6,
    average_days_to_next_signal: 28,
    ...overrides,
  };
}

function makeCoverageRow(
  overrides: Partial<SignalBacktestCoverageRow> = {},
): SignalBacktestCoverageRow {
  return {
    signal_run_id: "sig-1",
    readiness_status_at_signal: "analysis_ready",
    data_quality_status_at_signal: "healthy",
    sector_at_signal: "Technology",
    has_price_30d: true,
    has_price_90d: true,
    has_price_180d: true,
    has_price_365d: true,
    ...overrides,
  };
}

function makeInterpretationSummary(
  overrides: Partial<SignalBacktestInterpretationSummaryRow> = {},
): SignalBacktestInterpretationSummaryRow {
  return {
    total_observations: 180,
    evaluatable_observations: 150,
    historical_coverage_pct: 0.62,
    earliest_signal_date: "2025-01-01",
    latest_signal_date: "2025-10-01",
    signal_history_days: 273,
    dataset_maturity: "MEDIUM",
    ...overrides,
  };
}

describe("SignalValidationPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchSignalBacktestSummaryByBucket).mockResolvedValue([
      makeBucketRow(),
      makeBucketRow({ final_signal: "sell", horizon_days: 90, average_return: -0.03, median_return: -0.01, hit_rate: 0.35 }),
    ]);
    vi.mocked(fetchSignalBacktestSummaryByHorizon).mockResolvedValue([
      makeHorizonRow(),
      makeHorizonRow({ horizon_days: 90, observation_count: 35, covered_observation_count: 28, average_return: 0.02, median_return: 0.01, hit_rate: 0.51, coverage_pct: 0.8 }),
    ]);
    vi.mocked(fetchSignalBacktestByReadiness).mockResolvedValue([
      makeSegmentRow({ readiness_status_at_signal: "unknown" }),
    ]);
    vi.mocked(fetchSignalBacktestByDataQuality).mockResolvedValue([
      makeSegmentRow({ data_quality_status_at_signal: "critical", final_signal: "sell", horizon_days: 90 }),
    ]);
    vi.mocked(fetchSignalBacktestBySector).mockResolvedValue([
      makeSegmentRow({ sector_at_signal: "Financials", final_signal: "hold", horizon_days: 180 }),
    ]);
    vi.mocked(fetchSignalBacktestStability).mockResolvedValue([
      makeStabilityRow(),
      makeStabilityRow({ signal_bucket: "sell", flip_rate: 0.7, stability_pct: 0.3, flip_count: 7, stable_transition_count: 3 }),
    ]);
    vi.mocked(fetchSignalBacktestCoverageRows).mockResolvedValue([
      makeCoverageRow({
        signal_run_id: "sig-1",
        readiness_status_at_signal: null,
        has_price_90d: false,
      }),
      makeCoverageRow({
        signal_run_id: "sig-2",
        data_quality_status_at_signal: null,
        sector_at_signal: null,
        has_price_180d: false,
        has_price_365d: false,
      }),
    ]);
    vi.mocked(fetchSignalBacktestInterpretationSummary).mockResolvedValue(
      makeInterpretationSummary(),
    );
  });

  it("renders the interpretation panel, coverage summary, and research caveats", async () => {
    render(<SignalValidationPage />);

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /Signal Validation/i })).toBeInTheDocument(),
    );
    expect(screen.getByText(/Can I trust this model yet\?/i)).toBeInTheDocument();
    expect(screen.getByText(/Dataset maturity reflects the quality and coverage of the historical evidence so far/i)).toBeInTheDocument();
    expect(screen.getByText(/MEDIUM/i)).toBeInTheDocument();
    expect(screen.getByText(/Partially\. There is enough history to start learning from the signal behavior/i)).toBeInTheDocument();
    expect(screen.getByText(/This is price-return-only historical validation, not a strategy simulation and not a future guarantee\./i)).toBeInTheDocument();
    expect(screen.getByText(/Historical coverage/i)).toBeInTheDocument();
    expect(screen.getByText(/Evaluatable observations/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Total observations/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Earliest signal date/i)).toBeInTheDocument();
    expect(screen.getByText(/Latest signal date/i)).toBeInTheDocument();
    expect(screen.getByText(/Price return only\. Historical validation only\./i)).toBeInTheDocument();
    expect(screen.getAllByText(/not a strategy simulation/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Readiness at signal may be sparse/i)).toBeInTheDocument();
    expect(screen.getByText(/Missing forward prices remain not available rather than estimated/i)).toBeInTheDocument();
    expect(screen.getAllByText(/30d coverage/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Unknown readiness at signal/i)).toBeInTheDocument();
    expect(screen.getByText(/Unknown data quality at signal/i)).toBeInTheDocument();
    expect(screen.getByText(/Unknown sector at signal/i)).toBeInTheDocument();
    expect(screen.getByText(/90d coverage gap/i)).toBeInTheDocument();
    expect(screen.getByText(/365d coverage gap/i)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /Signal validation horizon comparison/i })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /Signal validation returns by signal bucket/i })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /Readiness breakdown/i })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /Data-quality breakdown/i })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /Sector breakdown/i })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /Signal stability/i })).toBeInTheDocument();
    expect(screen.getAllByText(/Buy/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Sell/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Unknown/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Critical/i)).toBeInTheDocument();
    expect(screen.getByText(/Financials/i)).toBeInTheDocument();
    expect(screen.queryByText(/buy\/sell recommendation/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/proven/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/reliable/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/outperform/i)).not.toBeInTheDocument();
  });

  it("shows a safe empty state when no observations exist", async () => {
    vi.mocked(fetchSignalBacktestSummaryByBucket).mockResolvedValue([]);
    vi.mocked(fetchSignalBacktestSummaryByHorizon).mockResolvedValue([]);
    vi.mocked(fetchSignalBacktestByReadiness).mockResolvedValue([]);
    vi.mocked(fetchSignalBacktestByDataQuality).mockResolvedValue([]);
    vi.mocked(fetchSignalBacktestBySector).mockResolvedValue([]);
    vi.mocked(fetchSignalBacktestStability).mockResolvedValue([]);
    vi.mocked(fetchSignalBacktestCoverageRows).mockResolvedValue([]);
    vi.mocked(fetchSignalBacktestInterpretationSummary).mockResolvedValue(
      makeInterpretationSummary({
        total_observations: 0,
        evaluatable_observations: 0,
        historical_coverage_pct: 0,
        earliest_signal_date: null,
        latest_signal_date: null,
        signal_history_days: null,
        dataset_maturity: "LOW",
      }),
    );

    render(<SignalValidationPage />);

    await waitFor(() =>
      expect(screen.getByText(/No historical validation observations yet/i)).toBeInTheDocument(),
    );
  });

  it("renders low-maturity interpretation conservatively", async () => {
    vi.mocked(fetchSignalBacktestInterpretationSummary).mockResolvedValue(
      makeInterpretationSummary({
        total_observations: 40,
        evaluatable_observations: 22,
        historical_coverage_pct: 0.35,
        earliest_signal_date: "2025-01-01",
        latest_signal_date: "2025-03-01",
        signal_history_days: 59,
        dataset_maturity: "LOW",
      }),
    );

    render(<SignalValidationPage />);

    await waitFor(() =>
      expect(screen.getByText(/Not yet\. The historical sample is still small or coverage is incomplete/i)).toBeInTheDocument(),
    );
  });

  it("renders high-maturity interpretation conservatively", async () => {
    vi.mocked(fetchSignalBacktestInterpretationSummary).mockResolvedValue(
      makeInterpretationSummary({
        total_observations: 420,
        evaluatable_observations: 390,
        historical_coverage_pct: 0.82,
        earliest_signal_date: "2024-01-01",
        latest_signal_date: "2025-06-01",
        signal_history_days: 517,
        dataset_maturity: "HIGH",
      }),
    );

    render(<SignalValidationPage />);

    await waitFor(() =>
      expect(screen.getByText(/More than before, but still cautiously\./i)).toBeInTheDocument(),
    );
  });
});
