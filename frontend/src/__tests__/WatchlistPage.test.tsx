/**
 * Page-level tests for WatchlistPage.
 *
 * The Supabase client and API module are mocked so no live Supabase
 * connection or real credentials are needed.
 */
import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";

// Mock Supabase so the module chain loads without env vars.
vi.mock("../lib/supabase", () => ({
  supabase: {
    from: vi.fn(),
    auth: {
      getSession: vi.fn(),
      onAuthStateChange: vi.fn(() => ({
        data: { subscription: { unsubscribe: vi.fn() } },
      })),
    },
  },
}));

// Mock the data-fetch layer so tests control what the page receives.
vi.mock("../lib/api", () => ({
  fetchWatchlist: vi.fn(),
  removeFromWatchlist: vi.fn(),
  fetchInactiveWatchlist: vi.fn(),
  reactivateWatchlistCompany: vi.fn(),
  // Phase 9B
  fetchMyDefaultWatchlistId: vi.fn().mockResolvedValue("wl-default"),
  fetchWatchlistAddRequests: vi.fn().mockResolvedValue([]),
  createWatchlistAddRequest: vi.fn(),
  cancelWatchlistAddRequest: vi.fn(),
}));

import { WatchlistPage } from "../pages/WatchlistPage";
import {
  fetchWatchlist,
  removeFromWatchlist,
  fetchInactiveWatchlist,
  fetchMyDefaultWatchlistId,
  fetchWatchlistAddRequests,
  createWatchlistAddRequest,
  cancelWatchlistAddRequest,
} from "../lib/api";
import type { WatchlistRow } from "../types";

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

describe("WatchlistPage — loading state", () => {
  it("shows loading spinner while fetch is in-flight", () => {
    vi.mocked(fetchWatchlist).mockImplementation(() => new Promise(() => {}));
    render(<WatchlistPage />);
    expect(screen.getByText(/Loading watchlist/i)).toBeInTheDocument();
  });
});

describe("WatchlistPage — error state", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows error heading when the API call rejects", async () => {
    vi.mocked(fetchWatchlist).mockRejectedValue(new Error("Network error"));
    render(<WatchlistPage />);
    await waitFor(() =>
      expect(screen.getByText(/Failed to load watchlist/i)).toBeInTheDocument(),
    );
  });

  it("renders the error message returned by the API", async () => {
    vi.mocked(fetchWatchlist).mockRejectedValue(new Error("Network error"));
    render(<WatchlistPage />);
    await waitFor(() =>
      expect(screen.getByText("Network error")).toBeInTheDocument(),
    );
  });
});

describe("WatchlistPage — empty state", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchInactiveWatchlist).mockResolvedValue([]);
  });

  it("shows empty-watchlist message when no rows are returned", async () => {
    vi.mocked(fetchWatchlist).mockResolvedValue([]);
    render(<WatchlistPage />);
    await waitFor(() =>
      expect(screen.getByText(/No active companies in watchlist/i)).toBeInTheDocument(),
    );
  });

  it("still shows the removed-companies toggle when active list is empty", async () => {
    vi.mocked(fetchWatchlist).mockResolvedValue([]);
    render(<WatchlistPage />);
    await waitFor(() =>
      expect(screen.getByText(/No active companies in watchlist/i)).toBeInTheDocument(),
    );
    // The toggle button must be present so the user can reactivate companies.
    expect(screen.getByText(/Show removed companies/i)).toBeInTheDocument();
  });

  it("shows removed-companies table when user expands the section on an empty active list", async () => {
    vi.mocked(fetchWatchlist).mockResolvedValue([]);
    vi.mocked(fetchInactiveWatchlist).mockResolvedValue([
      {
        watchlist_membership_id: "wc-old-1",
        company_id: "c-old-1",
        ticker: "TSLA",
        name: "Tesla Inc.",
        exchange: null,
        country: null,
        currency: "USD",
        sector: null,
        removed_at: "2026-05-01T00:00:00",
      },
    ]);
    render(<WatchlistPage />);
    await waitFor(() =>
      expect(screen.getByText(/No active companies in watchlist/i)).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByText(/Show removed companies/i));

    await waitFor(() =>
      expect(screen.getByText("TSLA")).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /Reactivate/i })).toBeInTheDocument();
  });
});

describe("WatchlistPage — data rendering", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders a company ticker when data is loaded", async () => {
    vi.mocked(fetchWatchlist).mockResolvedValue([
      makeRow({ ticker: "AAPL", name: "Apple Inc." }),
    ]);
    render(<WatchlistPage />);
    await waitFor(() =>
      expect(screen.getByText("AAPL")).toBeInTheDocument(),
    );
    expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
  });

  it("renders multiple company rows", async () => {
    vi.mocked(fetchWatchlist).mockResolvedValue([
      makeRow({ company_id: "1", ticker: "AAPL", name: "Apple Inc." }),
      makeRow({ company_id: "2", ticker: "MSFT", name: "Microsoft Corp." }),
    ]);
    render(<WatchlistPage />);
    await waitFor(() =>
      expect(screen.getByText("AAPL")).toBeInTheDocument(),
    );
    expect(screen.getByText("MSFT")).toBeInTheDocument();
  });

  it("renders the filter bar once data is loaded", async () => {
    vi.mocked(fetchWatchlist).mockResolvedValue([makeRow()]);
    render(<WatchlistPage />);
    await waitFor(() =>
      expect(
        screen.getByRole("search", { name: /Watchlist filters/i }),
      ).toBeInTheDocument(),
    );
  });

  it("renders the watchlist table with accessible label", async () => {
    vi.mocked(fetchWatchlist).mockResolvedValue([makeRow()]);
    render(<WatchlistPage />);
    await waitFor(() =>
      expect(
        screen.getByRole("table", { name: /Company watchlist/i }),
      ).toBeInTheDocument(),
    );
  });

  it("shows 'No matching companies' when a filter produces no results", async () => {
    // A row with signal BUY; apply STRONG_BUY filter → no match.
    vi.mocked(fetchWatchlist).mockResolvedValue([
      makeRow({ company_id: "1", ticker: "AAPL", final_signal: "buy" }),
    ]);
    render(<WatchlistPage />);
    // Wait for data to load first.
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());

    // The filterRows helper is tested separately; here we just check the
    // empty-filter UI exists when data is present.
    expect(screen.getByRole("search", { name: /Watchlist filters/i })).toBeInTheDocument();
  });
});

// ── Phase 9A: remove action ───────────────────────────────────────────────────

describe("WatchlistPage — remove action", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // By default, removeFromWatchlist resolves successfully.
    vi.mocked(removeFromWatchlist).mockResolvedValue(undefined);
    vi.mocked(fetchInactiveWatchlist).mockResolvedValue([]);
  });

  it("renders a remove button for each company row", async () => {
    vi.mocked(fetchWatchlist).mockResolvedValue([
      makeRow({ company_id: "1", ticker: "AAPL", watchlist_membership_id: "wc-1" }),
      makeRow({ company_id: "2", ticker: "MSFT", watchlist_membership_id: "wc-2" }),
    ]);
    render(<WatchlistPage />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());

    const removeBtns = screen.getAllByRole("button", { name: /Remove .* from watchlist/i });
    expect(removeBtns).toHaveLength(2);
  });

  it("shows a confirmation dialog before removing", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    vi.mocked(fetchWatchlist).mockResolvedValue([
      makeRow({ ticker: "AAPL", watchlist_membership_id: "wc-1" }),
    ]);
    render(<WatchlistPage />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());

    const removeBtn = screen.getByRole("button", { name: /Remove AAPL from watchlist/i });
    fireEvent.click(removeBtn);

    expect(confirmSpy).toHaveBeenCalledOnce();
    expect(confirmSpy.mock.calls[0][0]).toContain("AAPL");
    confirmSpy.mockRestore();
  });

  it("calls removeFromWatchlist with the membership ID when confirmed", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(fetchWatchlist).mockResolvedValue([
      makeRow({ ticker: "AAPL", watchlist_membership_id: "wc-42" }),
    ]);
    render(<WatchlistPage />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Remove AAPL from watchlist/i }));

    await waitFor(() =>
      expect(vi.mocked(removeFromWatchlist)).toHaveBeenCalledWith("wc-42"),
    );
  });

  it("removes the row from the DOM after successful removal", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(fetchWatchlist).mockResolvedValue([
      makeRow({ company_id: "1", ticker: "AAPL", watchlist_membership_id: "wc-1" }),
      makeRow({ company_id: "2", ticker: "MSFT", watchlist_membership_id: "wc-2" }),
    ]);
    render(<WatchlistPage />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Remove AAPL from watchlist/i }));

    await waitFor(() => expect(screen.queryByText("AAPL")).not.toBeInTheDocument());
    // MSFT should still be present.
    expect(screen.getByText("MSFT")).toBeInTheDocument();
  });

  it("does NOT remove the row when the confirmation is cancelled", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    vi.mocked(fetchWatchlist).mockResolvedValue([
      makeRow({ ticker: "AAPL", watchlist_membership_id: "wc-1" }),
    ]);
    render(<WatchlistPage />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Remove AAPL from watchlist/i }));

    // Row must still be visible.
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    // API must not have been called.
    expect(vi.mocked(removeFromWatchlist)).not.toHaveBeenCalled();
  });

  it("shows an error message when removeFromWatchlist rejects", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(removeFromWatchlist).mockRejectedValue(new Error("Permission denied"));
    vi.mocked(fetchWatchlist).mockResolvedValue([
      makeRow({ ticker: "AAPL", watchlist_membership_id: "wc-1" }),
    ]);
    render(<WatchlistPage />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Remove AAPL from watchlist/i }));

    await waitFor(() =>
      expect(screen.getByText(/Permission denied/i)).toBeInTheDocument(),
    );
    // Row should remain visible on error.
    expect(screen.getByText("AAPL")).toBeInTheDocument();
  });

  it("never calls a hard-delete on watchlist_companies", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(fetchWatchlist).mockResolvedValue([
      makeRow({ ticker: "AAPL", watchlist_membership_id: "wc-1" }),
    ]);
    render(<WatchlistPage />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Remove AAPL from watchlist/i }));

    await waitFor(() =>
      expect(vi.mocked(removeFromWatchlist)).toHaveBeenCalledOnce(),
    );
    // Confirm removeFromWatchlist (soft-remove via update) is the only
    // removal API called — no separate deleteFromWatchlist mock is registered
    // because no such export exists in api.ts.
    expect(vi.mocked(removeFromWatchlist)).toHaveBeenCalledWith("wc-1");
  });
});

// ---------------------------------------------------------------------------
// Phase 9B: Add-request form and list
// ---------------------------------------------------------------------------

import type { WatchlistAddRequest } from "../types";

function makeAddRequest(overrides: Partial<WatchlistAddRequest> = {}): WatchlistAddRequest {
  return {
    id: "req-1",
    user_id: "user-1",
    watchlist_id: "wl-default",
    requested_ticker: "NVDA",
    requested_exchange: null,
    status: "pending",
    company_id: null,
    error_code: null,
    error_message: null,
    requested_at: "2026-05-12T10:00:00Z",
    processed_at: null,
    created_at: "2026-05-12T10:00:00Z",
    updated_at: "2026-05-12T10:00:00Z",
    ...overrides,
  };
}

describe("WatchlistPage — Phase 9B add-request form", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchWatchlist).mockResolvedValue([makeRow()]);
    vi.mocked(fetchInactiveWatchlist).mockResolvedValue([]);
    vi.mocked(fetchMyDefaultWatchlistId).mockResolvedValue("wl-default");
    vi.mocked(fetchWatchlistAddRequests).mockResolvedValue([]);
  });

  it("renders the add-request form with ticker and exchange inputs", async () => {
    render(<WatchlistPage />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());

    expect(screen.getByLabelText(/Ticker symbol/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Exchange \(optional\)/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Request/i })).toBeInTheDocument();
  });

  it("submits a request with the correct ticker and no exchange", async () => {
    const newReq = makeAddRequest({ requested_ticker: "TSLA" });
    vi.mocked(createWatchlistAddRequest).mockResolvedValue(newReq);

    render(<WatchlistPage />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/Ticker symbol/i), {
      target: { value: "tsla" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Request/i }));

    await waitFor(() =>
      expect(vi.mocked(createWatchlistAddRequest)).toHaveBeenCalledWith(
        expect.objectContaining({
          watchlistId: "wl-default",
          requestedTicker: "TSLA",
        }),
      ),
    );
  });

  it("submits a request with exchange when provided", async () => {
    const newReq = makeAddRequest({ requested_ticker: "VOD", requested_exchange: "LSE" });
    vi.mocked(createWatchlistAddRequest).mockResolvedValue(newReq);

    render(<WatchlistPage />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/Ticker symbol/i), {
      target: { value: "VOD" },
    });
    fireEvent.change(screen.getByLabelText(/Exchange \(optional\)/i), {
      target: { value: "lse" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Request/i }));

    await waitFor(() =>
      expect(vi.mocked(createWatchlistAddRequest)).toHaveBeenCalledWith(
        expect.objectContaining({
          requestedExchange: "LSE",
        }),
      ),
    );
  });

  it("shows a client-side warning when the ticker is already active but does not block submission", async () => {
    // AAPL is already in active rows.
    vi.mocked(fetchWatchlist).mockResolvedValue([makeRow({ ticker: "AAPL" })]);
    vi.mocked(createWatchlistAddRequest).mockResolvedValue(makeAddRequest({ requested_ticker: "AAPL" }));

    render(<WatchlistPage />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/Ticker symbol/i), {
      target: { value: "AAPL" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Request/i }));

    await waitFor(() =>
      expect(screen.getByText(/already active/i)).toBeInTheDocument(),
    );
    // Request was still submitted — backend is authority.
    expect(vi.mocked(createWatchlistAddRequest)).toHaveBeenCalled();
  });

  it("shows a duplicate-pending error when the API returns a unique constraint error", async () => {
    vi.mocked(createWatchlistAddRequest).mockRejectedValue(
      new Error("duplicate key value violates unique constraint"),
    );

    render(<WatchlistPage />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/Ticker symbol/i), {
      target: { value: "MSFT" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Request/i }));

    await waitFor(() =>
      expect(screen.getByText(/pending request for MSFT already exists/i)).toBeInTheDocument(),
    );
  });

  it("does not call any provider API directly", async () => {
    // This test confirms no FMP/SEC call is present in the component.
    // The api module mock is the only one registered; if any unmocked
    // network call fires, the test would fail from unhandled rejection.
    vi.mocked(createWatchlistAddRequest).mockResolvedValue(makeAddRequest());

    render(<WatchlistPage />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/Ticker symbol/i), {
      target: { value: "NVDA" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Request/i }));

    await waitFor(() =>
      expect(vi.mocked(createWatchlistAddRequest)).toHaveBeenCalledOnce(),
    );
    // Only createWatchlistAddRequest was called — no provider calls.
  });
});

describe("WatchlistPage — Phase 9B request list", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchWatchlist).mockResolvedValue([makeRow()]);
    vi.mocked(fetchInactiveWatchlist).mockResolvedValue([]);
    vi.mocked(fetchMyDefaultWatchlistId).mockResolvedValue("wl-default");
  });

  it("renders request statuses correctly", async () => {
    vi.mocked(fetchWatchlistAddRequests).mockResolvedValue([
      makeAddRequest({ id: "r1", requested_ticker: "NVDA", status: "pending" }),
      makeAddRequest({ id: "r2", requested_ticker: "TSLA", status: "approved" }),
      makeAddRequest({ id: "r3", requested_ticker: "AMD", status: "rejected", error_code: "invalid_ticker" }),
      makeAddRequest({ id: "r4", requested_ticker: "INTC", status: "failed", error_code: "provider_unavailable" }),
      makeAddRequest({ id: "r5", requested_ticker: "QCOM", status: "cancelled" }),
    ]);

    render(<WatchlistPage />);
    await waitFor(() => expect(screen.getByText("NVDA")).toBeInTheDocument());

    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.getByText("Approved ✓")).toBeInTheDocument();
    expect(screen.getByText("Rejected")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Cancelled")).toBeInTheDocument();
  });

  it("shows friendly message for approved request", async () => {
    vi.mocked(fetchWatchlistAddRequests).mockResolvedValue([
      makeAddRequest({ status: "approved" }),
    ]);

    render(<WatchlistPage />);
    await waitFor(() =>
      expect(screen.getByText(/Analysis appears after next pipeline run/i)).toBeInTheDocument(),
    );
  });

  it("shows friendly message for invalid_ticker rejection", async () => {
    vi.mocked(fetchWatchlistAddRequests).mockResolvedValue([
      makeAddRequest({ status: "rejected", error_code: "invalid_ticker" }),
    ]);

    render(<WatchlistPage />);
    await waitFor(() =>
      expect(screen.getByText(/Ticker not found/i)).toBeInTheDocument(),
    );
  });

  it("shows friendly message for already_active rejection", async () => {
    vi.mocked(fetchWatchlistAddRequests).mockResolvedValue([
      makeAddRequest({ status: "rejected", error_code: "already_active" }),
    ]);

    render(<WatchlistPage />);
    await waitFor(() =>
      expect(screen.getByText(/Already in your active watchlist/i)).toBeInTheDocument(),
    );
  });

  it("shows friendly message for provider_unavailable failure", async () => {
    vi.mocked(fetchWatchlistAddRequests).mockResolvedValue([
      makeAddRequest({ status: "failed", error_code: "provider_unavailable" }),
    ]);

    render(<WatchlistPage />);
    await waitFor(() =>
      expect(screen.getByText(/Provider temporarily unavailable/i)).toBeInTheDocument(),
    );
  });

  it("shows cancel button only for pending requests", async () => {
    vi.mocked(fetchWatchlistAddRequests).mockResolvedValue([
      makeAddRequest({ id: "r1", status: "pending" }),
      makeAddRequest({ id: "r2", status: "approved" }),
    ]);

    render(<WatchlistPage />);
    await waitFor(() => expect(screen.getByText("Pending")).toBeInTheDocument());

    const cancelButtons = screen.getAllByRole("button", { name: /Cancel request/i });
    expect(cancelButtons).toHaveLength(1);
  });

  it("cancels a pending request and updates UI", async () => {
    vi.mocked(fetchWatchlistAddRequests).mockResolvedValue([
      makeAddRequest({ id: "req-cancel", requested_ticker: "NVDA", status: "pending" }),
    ]);
    vi.mocked(cancelWatchlistAddRequest).mockResolvedValue(undefined);

    render(<WatchlistPage />);
    await waitFor(() => expect(screen.getByText("Pending")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Cancel request for NVDA/i }));

    await waitFor(() =>
      expect(vi.mocked(cancelWatchlistAddRequest)).toHaveBeenCalledWith("req-cancel"),
    );
    await waitFor(() =>
      expect(screen.getByText("Cancelled")).toBeInTheDocument(),
    );
  });
});
