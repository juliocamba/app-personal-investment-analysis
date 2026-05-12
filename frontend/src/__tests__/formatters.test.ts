import {
  formatPrice,
  formatPct,
  formatNum,
  formatMarketCap,
  formatDate,
  formatDateTime,
} from "../lib/formatters";

describe("formatPrice", () => {
  it("formats a USD price correctly", () => {
    expect(formatPrice(123.45, "USD")).toBe("$123.45");
  });

  it("returns dash for null", () => {
    expect(formatPrice(null)).toBe("—");
  });

  it("returns dash for undefined", () => {
    expect(formatPrice(undefined)).toBe("—");
  });
});

describe("formatPct", () => {
  it("converts 0.253 to 25.3%", () => {
    expect(formatPct(0.253)).toBe("25.3%");
  });

  it("converts 1.0 to 100.0%", () => {
    expect(formatPct(1.0)).toBe("100.0%");
  });

  it("converts negative ratio correctly", () => {
    expect(formatPct(-0.05)).toBe("-5.0%");
  });

  it("returns dash for null", () => {
    expect(formatPct(null)).toBe("—");
  });

  it("respects decimals parameter", () => {
    expect(formatPct(0.1234, 2)).toBe("12.34%");
  });
});

describe("formatNum", () => {
  it("formats a number to 2 decimal places by default", () => {
    expect(formatNum(3.14159)).toBe("3.14");
  });

  it("returns dash for null", () => {
    expect(formatNum(null)).toBe("—");
  });

  it("respects decimals parameter", () => {
    expect(formatNum(42, 0)).toBe("42");
  });
});

describe("formatMarketCap", () => {
  it("formats trillions", () => {
    expect(formatMarketCap(2_500_000_000_000)).toBe("$2.5T");
  });

  it("formats billions", () => {
    expect(formatMarketCap(45_300_000_000)).toBe("$45.3B");
  });

  it("formats millions", () => {
    expect(formatMarketCap(890_000_000)).toBe("$890.0M");
  });

  it("returns dash for null", () => {
    expect(formatMarketCap(null)).toBe("—");
  });
});

describe("formatDate", () => {
  it("returns dash for null", () => {
    expect(formatDate(null)).toBe("—");
  });

  it("formats a valid ISO date string", () => {
    const result = formatDate("2024-01-15T00:00:00Z");
    // The exact format depends on locale, but it should not be the raw ISO string.
    expect(result).not.toBe("2024-01-15T00:00:00Z");
    expect(result.length).toBeGreaterThan(4);
  });
});

describe("formatDateTime", () => {
  it("returns dash for null", () => {
    expect(formatDateTime(null)).toBe("—");
  });

  it("formats a valid ISO timestamp", () => {
    const result = formatDateTime("2024-06-20T14:30:00Z");
    expect(result).not.toBe("—");
    expect(result.length).toBeGreaterThan(4);
  });
});
