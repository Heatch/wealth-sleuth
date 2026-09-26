import { describe, expect, it } from "vitest";
import { mergeData } from "./PerformanceChart";
import type { HistoryPoint, PortfolioHistory, BenchmarksHistoryResponse } from "../lib/types";

function pt(date: string, value: number, overrides: Partial<HistoryPoint> = {}): HistoryPoint {
  return { date, value, ...overrides };
}

describe("mergeData", () => {
  it("keeps only portfolio points when no benchmarks are active", () => {
    const history: PortfolioHistory = {
      series: [pt("2024-01-01", 100), pt("2024-01-02", 110)],
      period_start_value: 100,
      period_end_value: 110,
      currency: "CAD",
      available_years: [2024],
    };
    const merged = mergeData(history, undefined);
    expect(merged).toHaveLength(2);
    expect(merged[0].portfolio).toBe(100);
    expect(merged[1].portfolio).toBe(110);
  });

  it("keeps portfolio XIRR and TWR on the merged point", () => {
    const history: PortfolioHistory = {
      series: [pt("2024-01-02", 110, { return_xirr: 0.12, return_twr: 0.08 })],
      period_start_value: 110,
      period_end_value: 110,
      currency: "CAD",
      available_years: [2024],
    };
    const merged = mergeData(history, undefined);
    expect(merged[0].return_xirr).toBe(0.12);
    expect(merged[0].return_twr).toBe(0.08);
  });

  it("aligns portfolio and benchmark dates", () => {
    const history: PortfolioHistory = {
      series: [pt("2024-01-01", 100), pt("2024-01-03", 120)],
      period_start_value: 100,
      period_end_value: 120,
      currency: "CAD",
      available_years: [2024],
    };
    const benchmarks: BenchmarksHistoryResponse = {
      benchmarks: {
        SPY: {
          symbol: "SPY",
          display: "S&P 500",
          series: [pt("2024-01-02", 200), pt("2024-01-03", 210)],
          period_start_value: 200,
          period_end_value: 210,
          returns: {},
        },
      },
      currency: "CAD",
    };
    const merged = mergeData(history, benchmarks);
    expect(merged).toHaveLength(3);
    const jan2 = merged.find((p) => p.date === "2024-01-02");
    expect(jan2?.portfolio).toBeNull();
    expect(jan2?.benchmark_SPY).toBe(200);
  });

  it("merges benchmark returns onto shared points", () => {
    const history: PortfolioHistory = {
      series: [pt("2024-01-01", 100, { return_twr: 0 })] ,
      period_start_value: 100,
      period_end_value: 100,
      currency: "CAD",
      available_years: [2024],
    };
    const benchmarks: BenchmarksHistoryResponse = {
      benchmarks: {
        SPY: {
          symbol: "SPY",
          display: "S&P 500",
          series: [pt("2024-01-01", 200, { return_twr: 0.05 })],
          period_start_value: 200,
          period_end_value: 200,
          returns: {},
        },
      },
      currency: "CAD",
    };
    const merged = mergeData(history, benchmarks);
    expect(merged[0].return_twr_SPY).toBe(0.05);
  });
});
