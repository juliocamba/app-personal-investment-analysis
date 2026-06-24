/**
 * Tests for the pure filterRows/sortRows helpers exported from WatchlistPage.
 * Supabase is mocked so the module can load without real credentials.
 */
import { vi } from "vitest";

// Mock the Supabase client so the module tree can load without real env vars.
vi.mock("../lib/supabase", () => ({
  supabase: {
    from: vi.fn(),
    auth: { getSession: vi.fn(), onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })) },
  },
}));

import { filterRows, sortRows } from "../utils/watchlistFilters";
import type { WatchlistRow } from "../types";

function makeRow(overrides: Partial<WatchlistRow>): WatchlistRow {
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
    stored_final_signal: null,
    signal_display_state: null,
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
    data_quality_status: "no_diagnostics",
    data_quality_warning_codes: null,
    price_validation_status: null,
    statement_completeness_status: null,
    statement_completeness_summary: null,
    fundamentals_provider_comparison_status: null,
    fundamentals_provider_comparison_summary: null,
    quality_matrix_max_severity: null,
    quality_matrix_blocking_domains: null,
    quality_matrix_primary_codes: null,
    ...overrides,
  };
}

const rows: WatchlistRow[] = [
  makeRow({ company_id: "1", ticker: "AAPL", name: "Apple Inc.", final_signal: "BUY", p_buy_adjusted: 0.72, margin_of_safety_conservative: 0.25, final_quality_score: 80 }),
  makeRow({ company_id: "2", ticker: "MSFT", name: "Microsoft Corp.", final_signal: "HOLD", p_buy_adjusted: 0.45, margin_of_safety_conservative: 0.05, final_quality_score: 75 }),
  makeRow({ company_id: "3", ticker: "TSLA", name: "Tesla Inc.", final_signal: "SELL", p_buy_adjusted: 0.2, margin_of_safety_conservative: -0.1, final_quality_score: 50 }),
  makeRow({ company_id: "4", ticker: "GOOG", name: "Alphabet Inc.", final_signal: null, p_buy_adjusted: null, margin_of_safety_conservative: null, final_quality_score: null }),
];

// ---------------------------------------------------------------------------
// filterRows
// ---------------------------------------------------------------------------

describe("filterRows — signal filter", () => {
  it("returns all rows when filter is ALL", () => {
    expect(filterRows(rows, "ALL", "")).toHaveLength(4);
  });

  it("returns only BUY rows", () => {
    const result = filterRows(rows, "BUY", "");
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe("AAPL");
  });

  it("returns only SELL rows", () => {
    const result = filterRows(rows, "SELL", "");
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe("TSLA");
  });

  it("returns empty array when no signal matches", () => {
    expect(filterRows(rows, "STRONG_BUY", "")).toHaveLength(0);
  });

  it("filters rows with INSUFFICIENT_DATA signal (matches stored lowercase value)", () => {
    const dataRows = [
      makeRow({ company_id: "a", ticker: "NVDA", name: "Nvidia Corp.", final_signal: "insufficient_data" }),
      makeRow({ company_id: "b", ticker: "AAPL", name: "Apple Inc.", final_signal: "buy" }),
    ];
    const result = filterRows(dataRows, "INSUFFICIENT_DATA", "");
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe("NVDA");
  });
});

describe("filterRows — ticker search", () => {
  it("filters by ticker substring (case-insensitive)", () => {
    const result = filterRows(rows, "ALL", "aap");
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe("AAPL");
  });

  it("filters by company name substring", () => {
    const result = filterRows(rows, "ALL", "microsoft");
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe("MSFT");
  });

  it("ignores whitespace-only search", () => {
    expect(filterRows(rows, "ALL", "   ")).toHaveLength(4);
  });

  it("combines signal filter and search", () => {
    const result = filterRows(rows, "BUY", "apple");
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe("AAPL");
  });

  it("returns empty when search matches nothing", () => {
    expect(filterRows(rows, "ALL", "zzz")).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// sortRows
// ---------------------------------------------------------------------------

describe("sortRows", () => {
  it("sorts by ticker ascending", () => {
    const result = sortRows(rows, "ticker", true);
    expect(result.map((r) => r.ticker)).toEqual(["AAPL", "GOOG", "MSFT", "TSLA"]);
  });

  it("sorts by ticker descending", () => {
    const result = sortRows(rows, "ticker", false);
    expect(result[0].ticker).toBe("TSLA");
  });

  it("sorts by p_buy_adjusted descending, nulls last", () => {
    const result = sortRows(rows, "p_buy_adjusted", false);
    expect(result[0].ticker).toBe("AAPL");   // 0.72
    expect(result[1].ticker).toBe("MSFT");   // 0.45
    expect(result[result.length - 1].ticker).toBe("GOOG"); // null — always last
  });

  it("sorts by p_buy_adjusted ascending, nulls last", () => {
    const result = sortRows(rows, "p_buy_adjusted", true);
    expect(result[0].ticker).toBe("TSLA");  // 0.2
    expect(result[result.length - 1].ticker).toBe("GOOG"); // null — always last
  });

  it("sorts by margin_of_safety_conservative descending, nulls last", () => {
    const result = sortRows(rows, "margin_of_safety_conservative", false);
    expect(result[0].ticker).toBe("AAPL");  // 0.25
    expect(result[result.length - 1].ticker).toBe("GOOG"); // null last
  });

  it("does not mutate the original array", () => {
    const original = [...rows];
    sortRows(rows, "ticker", false);
    expect(rows).toEqual(original);
  });
});

// ---------------------------------------------------------------------------
// TRACKING_ONLY filter and HOLD exclusion (Phase 10C.4)
// ---------------------------------------------------------------------------

describe("filterRows — TRACKING_ONLY filter and HOLD exclusion", () => {
  const trackingRow = makeRow({
    company_id: "5",
    ticker: "ASML",
    name: "ASML Holding",
    final_signal: "hold",
    can_run_signal: false,
    readiness_status: "tracking_only",
  });
  const mixedRows = [...rows, trackingRow];

  it("TRACKING_ONLY filter returns only rows with can_run_signal = false", () => {
    const result = filterRows(mixedRows, "TRACKING_ONLY", "");
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe("ASML");
  });

  it("TRACKING_ONLY filter returns empty when no tracking rows exist", () => {
    expect(filterRows(rows, "TRACKING_ONLY", "")).toHaveLength(0);
  });

  it("HOLD filter excludes rows with can_run_signal = false", () => {
    const result = filterRows(mixedRows, "HOLD", "");
    expect(result.some((r) => r.ticker === "ASML")).toBe(false);
  });

  it("HOLD filter still includes rows with can_run_signal = null (legacy rows)", () => {
    const result = filterRows(mixedRows, "HOLD", "");
    expect(result.some((r) => r.ticker === "MSFT")).toBe(true);
  });

  it("ALL filter includes tracking-only rows", () => {
    const result = filterRows(mixedRows, "ALL", "");
    expect(result.some((r) => r.ticker === "ASML")).toBe(true);
  });

  it("TRACKING_ONLY filter respects search term", () => {
    const result = filterRows(mixedRows, "TRACKING_ONLY", "asml");
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe("ASML");
  });

  it("TRACKING_ONLY filter + non-matching search returns empty", () => {
    expect(filterRows(mixedRows, "TRACKING_ONLY", "zzz")).toHaveLength(0);
  });
});
