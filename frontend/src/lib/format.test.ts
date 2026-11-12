import { describe, expect, it } from "vitest";
import { formatValue, isStale } from "./format";

describe("formatValue", () => {
  it("formats numbers with fixed digits", () => {
    expect(formatValue(25.104)).toBe("25.10");
    expect(formatValue(0)).toBe("0.00");
    expect(formatValue(12.0346, 3)).toBe("12.035");
  });

  it("shows a dash for unavailable values instead of zero", () => {
    expect(formatValue(null)).toBe("—");
    expect(formatValue(undefined)).toBe("—");
    expect(formatValue(Number.NaN)).toBe("—");
  });
});

describe("isStale", () => {
  it("is stale after three poll intervals", () => {
    expect(isStale(0, 3000, 1)).toBe(false);
    expect(isStale(0, 3001, 1)).toBe(true);
  });
});
