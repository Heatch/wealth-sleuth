import { describe, expect, it } from "vitest";
import type { AllocationFilter, Holding } from "./types";
import { ALLOCATION_DIMENSIONS, matchesAllocationFilters, toggleAllocationFilter } from "./allocation";

function makeHolding(overrides: Partial<Holding> = {}): Holding {
  return {
    symbol: "X",
    name: "Test",
    brokerage: "B",
    account_type: "tfsa",
    asset_class: "stock",
    sector: "Technology",
    industry: "Software",
    country: "Canada",
    currency: "CAD",
    quantity: 1,
    avg_cost: 10,
    book_cost: 10,
    current_price: 12,
    current_value: 12,
    market_cap: null,
    trailing_pe: null,
    dividend_yield: null,
    gain: 2,
    gain_pct: 0.2,
    weight: null,
    day_change: null,
    day_change_pct: null,
    ...overrides,
  };
}

describe("matchesAllocationFilters", () => {
  it("passes everything when filters are empty", () => {
    expect(matchesAllocationFilters(makeHolding(), [])).toBe(true);
  });

  it("filters by a single dimension", () => {
    expect(matchesAllocationFilters(makeHolding({ sector: "Tech" }), [{ dimension: "sector", value: "Tech" }])).toBe(true);
    expect(matchesAllocationFilters(makeHolding({ sector: "Health" }), [{ dimension: "sector", value: "Tech" }])).toBe(false);
  });

  it("ORs multiple values within the same dimension", () => {
    const filters: { dimension: "sector"; value: string }[] = [
      { dimension: "sector", value: "Tech" },
      { dimension: "sector", value: "Health" },
    ];
    expect(matchesAllocationFilters(makeHolding({ sector: "Tech" }), filters)).toBe(true);
    expect(matchesAllocationFilters(makeHolding({ sector: "Health" }), filters)).toBe(true);
    expect(matchesAllocationFilters(makeHolding({ sector: "Energy" }), filters)).toBe(false);
  });

  it("ANDs values across dimensions", () => {
    const filters: { dimension: "sector" | "country"; value: string }[] = [
      { dimension: "sector", value: "Tech" },
      { dimension: "country", value: "Canada" },
    ];
    expect(matchesAllocationFilters(makeHolding({ sector: "Tech", country: "Canada" }), filters)).toBe(true);
    expect(matchesAllocationFilters(makeHolding({ sector: "Tech", country: "US" }), filters)).toBe(false);
    expect(matchesAllocationFilters(makeHolding({ sector: "Health", country: "Canada" }), filters)).toBe(false);
  });

  it("treats missing sector/country as Unknown", () => {
    expect(matchesAllocationFilters(makeHolding({ sector: null }), [{ dimension: "sector", value: "Unknown" }])).toBe(true);
  });

  it("supports multiple values in both dimensions", () => {
    const filters: { dimension: "sector" | "country"; value: string }[] = [
      { dimension: "sector", value: "Tech" },
      { dimension: "sector", value: "Health" },
      { dimension: "country", value: "Canada" },
      { dimension: "country", value: "US" },
    ];
    expect(matchesAllocationFilters(makeHolding({ sector: "Tech", country: "US" }), filters)).toBe(true);
    expect(matchesAllocationFilters(makeHolding({ sector: "Tech", country: "UK" }), filters)).toBe(false);
    expect(matchesAllocationFilters(makeHolding({ sector: "Energy", country: "Canada" }), filters)).toBe(false);
  });
});

describe("toggleAllocationFilter", () => {
  it("adds a new filter", () => {
    expect(toggleAllocationFilter([], "sector", "Tech")).toEqual([{ dimension: "sector", value: "Tech" }]);
  });

  it("removes an existing filter", () => {
    const filters: AllocationFilter[] = [{ dimension: "sector", value: "Tech" }];
    expect(toggleAllocationFilter(filters, "sector", "Tech")).toEqual([]);
  });

  it("keeps other filters when removing one", () => {
    const filters: AllocationFilter[] = [
      { dimension: "sector", value: "Tech" },
      { dimension: "country", value: "Canada" },
    ];
    expect(toggleAllocationFilter(filters, "sector", "Tech")).toEqual([{ dimension: "country", value: "Canada" }]);
  });
});

describe("ALLOCATION_DIMENSIONS", () => {
  it("contains the two dimensions used by the pies", () => {
    expect(ALLOCATION_DIMENSIONS).toEqual(["sector", "country"]);
  });
});
