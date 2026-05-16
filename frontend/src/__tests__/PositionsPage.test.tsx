import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  fetchCompaniesForPositions: vi.fn(),
  fetchPositions: vi.fn(),
  fetchPositionEntryProfiles: vi.fn(),
  fetchPositionReviewAlerts: vi.fn(),
  savePositionEntryProfile: vi.fn(),
  updatePositionReviewAlertLifecycle: vi.fn(),
  createPosition: vi.fn(),
  updatePosition: vi.fn(),
  closePosition: vi.fn(),
}));

import { PositionsPage } from "../pages/PositionsPage";
import {
  closePosition,
  createPosition,
  fetchCompaniesForPositions,
  fetchPositionEntryProfiles,
  fetchPositionReviewAlerts,
  fetchPositions,
  savePositionEntryProfile,
  updatePositionReviewAlertLifecycle,
  updatePosition,
} from "../lib/api";
import type {
  CompanyOption,
  PositionDashboardRow,
  PositionEntryProfileRow,
  PositionRow,
  PositionReviewAlertRow,
} from "../types";

function makeCompany(overrides: Partial<CompanyOption> = {}): CompanyOption {
  return {
    id: "company-1",
    ticker: "AAPL",
    name: "Apple Inc.",
    currency: "USD",
    ...overrides,
  };
}

function makePositionWriteRow(overrides: Partial<PositionRow> = {}): PositionRow {
  return {
    id: "pos-1",
    user_id: "user-1",
    company_id: "company-1",
    entry_date: "2026-05-01",
    quantity: 10,
    average_entry_price: 150,
    currency: "USD",
    fees: 5,
    notes: "Core position",
    status: "active",
    closed_at: null,
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    ...overrides,
  };
}

function makePositionViewRow(
  overrides: Partial<PositionDashboardRow> = {},
): PositionDashboardRow {
  return {
    id: "pos-1",
    user_id: "user-1",
    company_id: "company-1",
    ticker: "AAPL",
    name: "Apple Inc.",
    entry_date: "2026-05-01",
    quantity: 10,
    average_entry_price: 150,
    currency: "USD",
    fees: 5,
    notes: "Core position",
    status: "active",
    closed_at: null,
    price_date: "2026-05-15",
    current_price: 180,
    price_currency: "USD",
    cost_basis: 1505,
    current_value: 1800,
    unrealized_gain_loss: 295,
    unrealized_return_pct: 295 / 1505,
    current_signal: "hold",
    current_readiness_status: "analysis_ready",
    current_data_quality_status: "warning",
    current_quality_score: 79,
    current_valuation_low: 170,
    current_valuation_mid: 210,
    current_valuation_high: 250,
    current_margin_of_safety: 0.143,
    current_uncertainty_category: "moderate",
    ...overrides,
  };
}

function makeProfileRow(
  overrides: Partial<PositionEntryProfileRow> = {},
): PositionEntryProfileRow {
  return {
    id: "profile-1",
    position_id: "pos-1",
    user_id: "user-1",
    snapshot_taken_at: "2026-05-16T10:00:00Z",
    thesis_summary: "Compounding with resilient cash flows",
    why_bought: "Strong moat and recurring ecosystem demand",
    key_risks: "Regulatory pressure and slowing services growth",
    target_price: 220,
    target_price_currency: "USD",
    expected_holding_period: "3-5 years",
    confidence_level: "high",
    catalysts: "AI device cycle",
    invalidation_criteria: "ROIC erosion and negative revenue trend",
    entry_price: 180,
    entry_price_date: "2026-05-15",
    entry_price_currency: "USD",
    entry_signal: "buy",
    entry_readiness_status: "analysis_ready",
    entry_data_quality_status: "healthy",
    entry_quality_score: 82,
    entry_current_price: 180,
    entry_valuation_low: 160,
    entry_valuation_mid: 200,
    entry_valuation_high: 240,
    entry_margin_of_safety: 0.111,
    entry_uncertainty_category: "moderate",
    entry_snapshot_details: { p_buy: 0.68, p_sell: 0.12 },
    created_at: "2026-05-16T10:00:00Z",
    updated_at: "2026-05-16T10:00:00Z",
    ...overrides,
  };
}

function makeReviewAlertRow(
  overrides: Partial<PositionReviewAlertRow> = {},
): PositionReviewAlertRow {
  return {
    id: "alert-1",
    position_id: "pos-1",
    user_id: "user-1",
    company_id: "company-1",
    alert_type: "target_price_reached",
    severity: "warning",
    status: "open",
    title: "AAPL target price reached",
    message: "The latest stored price has reached or exceeded the manual target price.",
    details: {},
    dedupe_key: "pos-1:target_price_reached:220.0000:USD",
    triggered_at: "2026-05-16T10:00:00Z",
    first_seen_at: "2026-05-16T10:00:00Z",
    last_seen_at: "2026-05-16T10:00:00Z",
    resolved_at: null,
    dismissed_at: null,
    dismissed_reason: null,
    snoozed_until: null,
    created_at: "2026-05-16T10:00:00Z",
    updated_at: "2026-05-16T10:00:00Z",
    ...overrides,
  };
}

describe("PositionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchCompaniesForPositions).mockResolvedValue([makeCompany()]);
    vi.mocked(fetchPositions).mockResolvedValue([]);
    vi.mocked(fetchPositionEntryProfiles).mockResolvedValue([]);
    vi.mocked(fetchPositionReviewAlerts).mockResolvedValue([]);
  });

  it("shows loading state while data is loading", () => {
    vi.mocked(fetchPositions).mockImplementation(() => new Promise(() => {}));
    render(<PositionsPage />);
    expect(screen.getByText(/Loading positions/i)).toBeInTheDocument();
  });

  it("shows empty state when no positions exist", async () => {
    render(<PositionsPage />);
    await waitFor(() =>
      expect(screen.getByText(/No positions yet/i)).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/This does not change signals, readiness, or alerts/i),
    ).toBeInTheDocument();
  });

  it("renders a read-only entry-vs-current comparison with improved thesis display", async () => {
    vi.mocked(fetchPositions).mockResolvedValue([makePositionViewRow()]);
    vi.mocked(fetchPositionEntryProfiles).mockResolvedValue([makeProfileRow()]);
    vi.mocked(fetchPositionReviewAlerts).mockResolvedValue([makeReviewAlertRow()]);

    render(<PositionsPage />);

    await waitFor(() =>
      expect(screen.getByRole("table", { name: /Manual positions/i })).toBeInTheDocument(),
    );

    const table = screen.getByRole("table", { name: /Manual positions/i });
    expect(within(table).getByText("$295.00")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /Entry snapshots/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Compounding with resilient cash flows/i)).toBeInTheDocument();
    expect(screen.getByText(/Strong moat and recurring ecosystem demand/i)).toBeInTheDocument();
    expect(screen.getByText(/Entry vs current/i)).toBeInTheDocument();
    expect(screen.getByText("Buy")).toBeInTheDocument();
    expect(screen.getByText("Hold")).toBeInTheDocument();
    expect(screen.getByText("Healthy")).toBeInTheDocument();
    expect(screen.getAllByText("Warning").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("$160.00 / $200.00 / $240.00")).toBeInTheDocument();
    expect(screen.getByText("$170.00 / $210.00 / $250.00")).toBeInTheDocument();
    expect(screen.getByText("14.3%")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /Review alerts/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/AAPL target price reached/i)).toBeInTheDocument();
    expect(screen.getByText(/Triggered:/i)).toBeInTheDocument();
    expect(screen.getByText("Open")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Dismiss/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Snooze 30d/i })).toBeInTheDocument();
  });

  it("handles missing entry profiles and null current comparison values safely", async () => {
    vi.mocked(fetchPositions).mockResolvedValue([
      makePositionViewRow({
        current_signal: null,
        current_readiness_status: null,
        current_data_quality_status: null,
        current_quality_score: null,
        current_valuation_low: null,
        current_valuation_mid: null,
        current_valuation_high: null,
        current_margin_of_safety: null,
        current_uncertainty_category: null,
        current_price: null,
        price_currency: null,
        price_date: null,
      }),
    ]);
    vi.mocked(fetchPositionEntryProfiles).mockResolvedValue([
      makeProfileRow({
        thesis_summary: null,
        why_bought: null,
        key_risks: null,
        target_price: null,
        target_price_currency: null,
        expected_holding_period: null,
        confidence_level: null,
        catalysts: null,
        invalidation_criteria: null,
        entry_price: null,
        entry_price_date: null,
        entry_price_currency: null,
        entry_signal: null,
        entry_readiness_status: null,
        entry_data_quality_status: null,
        entry_quality_score: null,
        entry_current_price: null,
        entry_valuation_low: null,
        entry_valuation_mid: null,
        entry_valuation_high: null,
        entry_margin_of_safety: null,
        entry_uncertainty_category: null,
      }),
    ]);

    render(<PositionsPage />);

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /Entry snapshots/i })).toBeInTheDocument(),
    );
    expect(screen.getByText(/Entry vs current/i)).toBeInTheDocument();
    expect(screen.getAllByText("-").length).toBeGreaterThan(5);
    expect(screen.getByText(/No active review alerts\./i)).toBeInTheDocument();
  });

  it("creates a new manual position with optional thesis input", async () => {
    vi.mocked(fetchPositions)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        makePositionViewRow({
          id: "pos-2",
          notes: "Added manually",
        }),
      ]);
    vi.mocked(fetchPositionEntryProfiles)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        makeProfileRow({
          position_id: "pos-2",
          thesis_summary: "Undervalued cash machine",
          why_bought: "Valuation and quality setup",
        }),
      ]);
    vi.mocked(createPosition).mockResolvedValue(
      makePositionWriteRow({
        id: "pos-2",
        notes: "Added manually",
      }),
    );
    vi.mocked(savePositionEntryProfile).mockResolvedValue(
      makeProfileRow({
        position_id: "pos-2",
        thesis_summary: "Undervalued cash machine",
        why_bought: "Valuation and quality setup",
      }),
    );

    render(<PositionsPage />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Add position/i })).toBeInTheDocument(),
    );

    fireEvent.change(screen.getByLabelText("Entry date"), {
      target: { value: "2026-05-03" },
    });
    fireEvent.change(screen.getByLabelText("Quantity"), {
      target: { value: "12" },
    });
    fireEvent.change(screen.getByLabelText("Average entry price"), {
      target: { value: "155.5" },
    });
    fireEvent.change(screen.getByLabelText("Notes"), {
      target: { value: "Added manually" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Add entry thesis/i }));
    fireEvent.change(screen.getByLabelText("Thesis summary"), {
      target: { value: "Undervalued cash machine" },
    });
    fireEvent.change(screen.getByLabelText("Why I bought"), {
      target: { value: "Valuation and quality setup" },
    });

    fireEvent.click(screen.getByRole("button", { name: /Add position/i }));

    await waitFor(() =>
      expect(createPosition).toHaveBeenCalledWith({
        company_id: "company-1",
        entry_date: "2026-05-03",
        quantity: 12,
        average_entry_price: 155.5,
        currency: "USD",
        fees: null,
        notes: "Added manually",
        status: "active",
        closed_at: null,
      }),
    );
    await waitFor(() =>
      expect(savePositionEntryProfile).toHaveBeenCalledWith("pos-2", {
        thesis_summary: "Undervalued cash machine",
        why_bought: "Valuation and quality setup",
        key_risks: "",
        target_price: null,
        target_price_currency: "USD",
        expected_holding_period: "",
        confidence_level: null,
        catalysts: "",
        invalidation_criteria: "",
      }),
    );
    await waitFor(() => expect(fetchPositions).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(fetchPositionEntryProfiles).toHaveBeenCalledTimes(2));
  });

  it("edits ownership fields and thesis fields separately from frozen snapshot values", async () => {
    vi.mocked(fetchPositions)
      .mockResolvedValueOnce([makePositionViewRow()])
      .mockResolvedValueOnce([
        makePositionViewRow({
          average_entry_price: 145,
        }),
      ]);
    vi.mocked(fetchPositionEntryProfiles)
      .mockResolvedValueOnce([makeProfileRow()])
      .mockResolvedValueOnce([
        makeProfileRow({
          why_bought: "Updated thesis note",
        }),
      ]);
    vi.mocked(updatePosition).mockResolvedValue(
      makePositionWriteRow({
        average_entry_price: 145,
      }),
    );
    vi.mocked(savePositionEntryProfile).mockResolvedValue(
      makeProfileRow({
        why_bought: "Updated thesis note",
      }),
    );

    render(<PositionsPage />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Edit/i }));
    fireEvent.change(screen.getByLabelText("Average entry price"), {
      target: { value: "145" },
    });
    fireEvent.change(screen.getByLabelText("Why I bought"), {
      target: { value: "Updated thesis note" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Save changes/i }));

    await waitFor(() =>
      expect(updatePosition).toHaveBeenCalledWith("pos-1", {
        company_id: "company-1",
        entry_date: "2026-05-01",
        quantity: 10,
        average_entry_price: 145,
        currency: "USD",
        fees: 5,
        notes: "Core position",
        status: "active",
        closed_at: null,
      }),
    );
    await waitFor(() =>
      expect(savePositionEntryProfile).toHaveBeenCalledWith("pos-1", {
        thesis_summary: "Compounding with resilient cash flows",
        why_bought: "Updated thesis note",
        key_risks: "Regulatory pressure and slowing services growth",
        target_price: 220,
        target_price_currency: "USD",
        expected_holding_period: "3-5 years",
        confidence_level: "high",
        catalysts: "AI device cycle",
        invalidation_criteria: "ROIC erosion and negative revenue trend",
      }),
    );
  });

  it("dismisses an open review alert and refreshes the active review section", async () => {
    vi.mocked(fetchPositions)
      .mockResolvedValueOnce([makePositionViewRow()])
      .mockResolvedValueOnce([makePositionViewRow()]);
    vi.mocked(fetchPositionEntryProfiles)
      .mockResolvedValueOnce([makeProfileRow()])
      .mockResolvedValueOnce([makeProfileRow()]);
    vi.mocked(fetchPositionReviewAlerts)
      .mockResolvedValueOnce([makeReviewAlertRow()])
      .mockResolvedValueOnce([]);
    vi.mocked(updatePositionReviewAlertLifecycle).mockResolvedValue(
      makeReviewAlertRow({
        status: "dismissed",
        dismissed_reason: "dismissed_in_ui",
      }),
    );

    render(<PositionsPage />);
    await waitFor(() => expect(screen.getByText(/AAPL target price reached/i)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Dismiss/i }));

    await waitFor(() =>
      expect(updatePositionReviewAlertLifecycle).toHaveBeenCalledWith("alert-1", {
        status: "dismissed",
        dismissed_reason: "dismissed_in_ui",
      }),
    );
    await waitFor(() =>
      expect(screen.getByText(/No active review alerts\./i)).toBeInTheDocument(),
    );
  });

  it("snoozes a review alert and shows the snoozed status clearly", async () => {
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(
      new Date("2026-05-16T10:00:00.000Z").valueOf(),
    );
    vi.mocked(fetchPositions)
      .mockResolvedValueOnce([makePositionViewRow()])
      .mockResolvedValueOnce([makePositionViewRow()]);
    vi.mocked(fetchPositionEntryProfiles)
      .mockResolvedValueOnce([makeProfileRow()])
      .mockResolvedValueOnce([makeProfileRow()]);
    vi.mocked(fetchPositionReviewAlerts)
      .mockResolvedValueOnce([makeReviewAlertRow()])
      .mockResolvedValueOnce([
        makeReviewAlertRow({
          status: "snoozed",
          snoozed_until: "2026-06-15T10:00:00.000Z",
        }),
      ]);
    vi.mocked(updatePositionReviewAlertLifecycle).mockResolvedValue(
      makeReviewAlertRow({
        status: "snoozed",
        snoozed_until: "2026-06-15T10:00:00.000Z",
      }),
    );

    render(<PositionsPage />);
    await waitFor(() => expect(screen.getByText(/AAPL target price reached/i)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Snooze 30d/i }));

    await waitFor(() =>
      expect(updatePositionReviewAlertLifecycle).toHaveBeenCalledWith("alert-1", {
        status: "snoozed",
        snoozed_until: "2026-06-15T10:00:00.000Z",
      }),
    );
    await waitFor(() => expect(screen.getByText("Snoozed")).toBeInTheDocument());
    expect(screen.getByText(/Snoozed until:/i)).toBeInTheDocument();

    nowSpy.mockRestore();
  });
});
