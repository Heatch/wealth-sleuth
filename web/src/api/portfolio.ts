// Thin API client for the FastAPI backend (proxied via vite.config.ts).
import type {
  Currency,
  HoldingSort,
  HoldingsResponse,
  Period,
  PortfolioHistory,
  PortfolioSummary,
  SortOrder,
} from "../lib/types";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export function fetchSummary(currency: Currency): Promise<PortfolioSummary> {
  return get<PortfolioSummary>(`/api/portfolio/summary?currency=${currency}`);
}

export function fetchHistory(period: Period, currency: Currency): Promise<PortfolioHistory> {
  return get<PortfolioHistory>(`/api/portfolio/history?period=${period}&currency=${currency}`);
}

export function fetchHoldings(
  currency: Currency,
  sort: HoldingSort = "value",
  order: SortOrder = "desc",
): Promise<HoldingsResponse> {
  return get<HoldingsResponse>(`/api/holdings?currency=${currency}&sort=${sort}&order=${order}`);
}

export interface StatusResponse {
  has_gaps: boolean;
  gaps: {
    missing: number[];
    stale: Array<{ id: number; last_date: string }>;
    fx_stale: boolean;
    today: string;
  };
}

export function fetchStatus(): Promise<StatusResponse> {
  return get<StatusResponse>(`/api/status`);
}

