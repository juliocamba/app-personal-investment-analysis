/**
 * Page-level tests for AlertsPage.
 *
 * The Supabase client and API module are mocked so no live Supabase
 * connection or real credentials are needed.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
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
  fetchAlertHistory: vi.fn(),
}));

import { AlertsPage } from "../pages/AlertsPage";
import { fetchAlertHistory } from "../lib/api";
import type { AlertHistoryRow } from "../types";

function makeAlert(overrides: Partial<AlertHistoryRow> = {}): AlertHistoryRow {
  return {
    id: "alert-1",
    alert_rule_id: null,
    company_id: null,
    channel: "email",
    title: "Signal changed: BUY",
    message: "p_buy_adjusted crossed 0.70",
    dedupe_key: "key-1",
    sent_at: "2024-06-01T10:00:00Z",
    status: "sent",
    error_message: null,
    created_at: "2024-06-01T10:00:00Z",
    ...overrides,
  };
}

describe("AlertsPage — loading state", () => {
  it("shows loading spinner while fetch is in-flight", () => {
    vi.mocked(fetchAlertHistory).mockImplementation(() => new Promise(() => {}));
    render(<AlertsPage />);
    expect(screen.getByText(/Loading alert history/i)).toBeInTheDocument();
  });
});

describe("AlertsPage — error state", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows error heading when the API call rejects", async () => {
    vi.mocked(fetchAlertHistory).mockRejectedValue(new Error("DB error"));
    render(<AlertsPage />);
    await waitFor(() =>
      expect(screen.getByText(/Failed to load alert history/i)).toBeInTheDocument(),
    );
  });

  it("renders the error message returned by the API", async () => {
    vi.mocked(fetchAlertHistory).mockRejectedValue(new Error("DB error"));
    render(<AlertsPage />);
    await waitFor(() =>
      expect(screen.getByText("DB error")).toBeInTheDocument(),
    );
  });

  it("does not mention backend environment variables in the error hint", async () => {
    vi.mocked(fetchAlertHistory).mockRejectedValue(new Error("fail"));
    render(<AlertsPage />);
    await waitFor(() =>
      expect(screen.getByText(/Failed to load alert history/i)).toBeInTheDocument(),
    );
    // ALERTS_ENABLED is a backend env var and must not appear in the UI.
    expect(screen.queryByText(/ALERTS_ENABLED/)).toBeNull();
  });
});

describe("AlertsPage — empty state", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows empty-alerts message when no rows are returned", async () => {
    vi.mocked(fetchAlertHistory).mockResolvedValue([]);
    render(<AlertsPage />);
    await waitFor(() =>
      expect(screen.getByText(/No alerts yet/i)).toBeInTheDocument(),
    );
  });

  it("does not mention backend environment variables in the empty state", async () => {
    vi.mocked(fetchAlertHistory).mockResolvedValue([]);
    render(<AlertsPage />);
    await waitFor(() =>
      expect(screen.getByText(/No alerts yet/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/ALERTS_ENABLED/)).toBeNull();
  });
});

describe("AlertsPage — data rendering", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders alert title when data is loaded", async () => {
    vi.mocked(fetchAlertHistory).mockResolvedValue([
      makeAlert({ title: "Signal changed: BUY" }),
    ]);
    render(<AlertsPage />);
    await waitFor(() =>
      expect(screen.getByText("Signal changed: BUY")).toBeInTheDocument(),
    );
  });

  it("renders channel and status badges", async () => {
    vi.mocked(fetchAlertHistory).mockResolvedValue([
      makeAlert({ channel: "telegram", status: "sent" }),
    ]);
    render(<AlertsPage />);
    await waitFor(() =>
      expect(screen.getByText("telegram")).toBeInTheDocument(),
    );
    expect(screen.getByText("sent")).toBeInTheDocument();
  });

  it("renders error_message for a failed alert", async () => {
    vi.mocked(fetchAlertHistory).mockResolvedValue([
      makeAlert({ status: "failed", error_message: "smtp_send_failed (SMTPException)" }),
    ]);
    render(<AlertsPage />);
    await waitFor(() =>
      expect(
        screen.getByText("smtp_send_failed (SMTPException)"),
      ).toBeInTheDocument(),
    );
  });

  it("renders multiple alert rows", async () => {
    vi.mocked(fetchAlertHistory).mockResolvedValue([
      makeAlert({ id: "a1", title: "Alert one" }),
      makeAlert({ id: "a2", title: "Alert two" }),
    ]);
    render(<AlertsPage />);
    await waitFor(() =>
      expect(screen.getByText("Alert one")).toBeInTheDocument(),
    );
    expect(screen.getByText("Alert two")).toBeInTheDocument();
  });

  it("renders the alert history table with accessible label", async () => {
    vi.mocked(fetchAlertHistory).mockResolvedValue([makeAlert()]);
    render(<AlertsPage />);
    await waitFor(() =>
      expect(
        screen.getByRole("table", { name: /Alert history/i }),
      ).toBeInTheDocument(),
    );
  });
});
