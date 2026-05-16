import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  fetchCompaniesForPositions: vi.fn(),
  fetchPositions: vi.fn(),
  createPosition: vi.fn(),
  updatePosition: vi.fn(),
  closePosition: vi.fn(),
}));

import { PositionsPage } from "../pages/PositionsPage";
import {
  closePosition,
  createPosition,
  fetchCompaniesForPositions,
  fetchPositions,
  updatePosition,
} from "../lib/api";
import type { CompanyOption, PositionDashboardRow, PositionRow } from "../types";

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
    ...overrides,
  };
}

describe("PositionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchCompaniesForPositions).mockResolvedValue([makeCompany()]);
    vi.mocked(fetchPositions).mockResolvedValue([]);
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

  it("renders computed display values from dashboard_positions_latest", async () => {
    vi.mocked(fetchPositions).mockResolvedValue([makePositionViewRow()]);

    render(<PositionsPage />);

    await waitFor(() =>
      expect(screen.getByRole("table", { name: /Manual positions/i })).toBeInTheDocument(),
    );

    const table = screen.getByRole("table", { name: /Manual positions/i });
    expect(within(table).getByText("AAPL")).toBeInTheDocument();
    expect(within(table).getByText("$180.00")).toBeInTheDocument();
    expect(within(table).getByText("$1,505.00")).toBeInTheDocument();
    expect(within(table).getByText("$1,800.00")).toBeInTheDocument();
    expect(within(table).getByText("$295.00")).toBeInTheDocument();
    expect(within(table).getByText("19.6%")).toBeInTheDocument();
    expect(within(table).getByText(/May 15, 2026/i)).toBeInTheDocument();
  });

  it("shows dash fallbacks when price-derived metrics are unavailable", async () => {
    vi.mocked(fetchPositions).mockResolvedValue([
      makePositionViewRow({
        current_price: null,
        price_date: null,
        price_currency: null,
        cost_basis: null,
        current_value: null,
        unrealized_gain_loss: null,
        unrealized_return_pct: null,
      }),
    ]);

    render(<PositionsPage />);

    await waitFor(() =>
      expect(screen.getByRole("table", { name: /Manual positions/i })).toBeInTheDocument(),
    );

    const table = screen.getByRole("table", { name: /Manual positions/i });
    expect(within(table).getAllByText("-").length).toBeGreaterThanOrEqual(4);
  });

  it("creates a new manual position and refreshes display metrics", async () => {
    vi.mocked(fetchPositions)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        makePositionViewRow({
          id: "pos-2",
          quantity: 12,
          average_entry_price: 155.5,
          notes: "Added manually",
          cost_basis: 1870.5,
          current_value: 2160,
          unrealized_gain_loss: 289.5,
          unrealized_return_pct: 289.5 / 1870.5,
        }),
      ]);
    vi.mocked(createPosition).mockResolvedValue(
      makePositionWriteRow({
        id: "pos-2",
        quantity: 12,
        average_entry_price: 155.5,
        notes: "Added manually",
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
    fireEvent.change(screen.getByLabelText("Fees"), {
      target: { value: "4.5" },
    });
    fireEvent.change(screen.getByLabelText("Notes"), {
      target: { value: "Added manually" },
    });

    fireEvent.click(screen.getByRole("button", { name: /Add position/i }));

    await waitFor(() =>
      expect(createPosition).toHaveBeenCalledWith({
        company_id: "company-1",
        entry_date: "2026-05-03",
        quantity: 12,
        average_entry_price: 155.5,
        currency: "USD",
        fees: 4.5,
        notes: "Added manually",
        status: "active",
        closed_at: null,
      }),
    );
    await waitFor(() => expect(fetchPositions).toHaveBeenCalledTimes(2));
    expect(screen.getByText("Added manually")).toBeInTheDocument();
  });

  it("edits an existing position and refreshes display metrics", async () => {
    vi.mocked(fetchPositions)
      .mockResolvedValueOnce([makePositionViewRow()])
      .mockResolvedValueOnce([
        makePositionViewRow({
          average_entry_price: 145,
          notes: "Updated thesis note",
          cost_basis: 1455,
          unrealized_gain_loss: 345,
          unrealized_return_pct: 345 / 1455,
        }),
      ]);
    vi.mocked(updatePosition).mockResolvedValue(
      makePositionWriteRow({
        average_entry_price: 145,
        notes: "Updated thesis note",
      }),
    );

    render(<PositionsPage />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Edit/i }));
    fireEvent.change(screen.getByLabelText("Average entry price"), {
      target: { value: "145" },
    });
    fireEvent.change(screen.getByLabelText("Notes"), {
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
        notes: "Updated thesis note",
        status: "active",
        closed_at: null,
      }),
    );
    await waitFor(() => expect(fetchPositions).toHaveBeenCalledTimes(2));
    expect(screen.getByText("Updated thesis note")).toBeInTheDocument();
  });

  it("closes an active position without touching analytics state", async () => {
    vi.mocked(fetchPositions)
      .mockResolvedValueOnce([makePositionViewRow()])
      .mockResolvedValueOnce([
        makePositionViewRow({
          status: "closed",
          closed_at: "2026-05-16T10:00:00Z",
          cost_basis: null,
          current_value: null,
          unrealized_gain_loss: null,
          unrealized_return_pct: null,
        }),
      ]);
    vi.mocked(closePosition).mockResolvedValue(
      makePositionWriteRow({
        status: "closed",
        closed_at: "2026-05-16T10:00:00Z",
      }),
    );

    render(<PositionsPage />);
    await waitFor(() => expect(screen.getByText("AAPL")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Close/i }));

    await waitFor(() => expect(closePosition).toHaveBeenCalledWith("pos-1"));
    await waitFor(() => expect(fetchPositions).toHaveBeenCalledTimes(2));
    const table = screen.getByRole("table", { name: /Manual positions/i });
    expect(within(table).getAllByText("Closed").length).toBeGreaterThanOrEqual(2);
  });
});
