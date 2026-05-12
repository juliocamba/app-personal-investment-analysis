import React from "react";
import { render, screen } from "@testing-library/react";
import { SignalBadge } from "../components/SignalBadge";

describe("SignalBadge", () => {
  it("renders BUY with green background", () => {
    render(<SignalBadge signal="BUY" />);
    const badge = screen.getByTestId("signal-badge");
    expect(badge).toHaveTextContent("BUY");
    expect(badge).toHaveStyle({ background: "#16a34a", color: "#fff" });
  });

  it("renders SELL with red background", () => {
    render(<SignalBadge signal="SELL" />);
    const badge = screen.getByTestId("signal-badge");
    expect(badge).toHaveTextContent("SELL");
    expect(badge).toHaveStyle({ background: "#dc2626", color: "#fff" });
  });

  it("renders HOLD with amber background", () => {
    render(<SignalBadge signal="HOLD" />);
    const badge = screen.getByTestId("signal-badge");
    expect(badge).toHaveTextContent("HOLD");
    expect(badge).toHaveStyle({ background: "#d97706" });
  });

  it("renders INSUFFICIENT_DATA with grey background", () => {
    render(<SignalBadge signal="insufficient_data" />);
    const badge = screen.getByTestId("signal-badge");
    expect(badge).toHaveTextContent("INSUFFICIENT_DATA");
    expect(badge).toHaveStyle({ background: "#94a3b8" });
  });

  it("renders STRONG_BUY", () => {
    render(<SignalBadge signal="STRONG_BUY" />);
    const badge = screen.getByTestId("signal-badge");
    expect(badge).toHaveTextContent("STRONG_BUY");
  });

  it("renders dash for null signal", () => {
    render(<SignalBadge signal={null} />);
    const badge = document.querySelector(".badge--unknown");
    expect(badge).not.toBeNull();
    expect(badge).toHaveTextContent("—");
  });

  it("is case-insensitive — 'buy' renders same as 'BUY'", () => {
    render(<SignalBadge signal="buy" />);
    const badge = screen.getByTestId("signal-badge");
    expect(badge).toHaveStyle({ background: "#16a34a" });
  });

  it("renders unknown signals with neutral style", () => {
    render(<SignalBadge signal="UNKNOWN_SIGNAL" />);
    const badge = screen.getByTestId("signal-badge");
    expect(badge).toHaveTextContent("UNKNOWN_SIGNAL");
    expect(badge).not.toHaveStyle({ background: "#16a34a" });
  });
});
