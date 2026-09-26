// Thin API client for the FastAPI backend (proxied via vite.config.ts).
import type {
  Account,
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

function withAccounts(url: string, accounts?: number[] | null): string {
  if (accounts && accounts.length) return `${url}&accounts=${accounts.join(",")}`;
  return url;
}

function withSymbols(url: string, symbols?: string[] | null): string {
  if (symbols && symbols.length) return `${url}&symbols=${encodeURIComponent(symbols.join(","))}`;
  return url;
}

export function fetchSummary(
  currency: Currency,
  accounts?: number[] | null,
  symbols?: string[] | null,
): Promise<PortfolioSummary> {
  let url = `/api/portfolio/summary?currency=${currency}`;
  url = withAccounts(url, accounts);
  url = withSymbols(url, symbols);
  return get<PortfolioSummary>(url);
}

export function fetchHistory(
  period: Period,
  currency: Currency,
  accounts?: number[] | null,
  symbols?: string[] | null,
): Promise<PortfolioHistory> {
  let url = `/api/portfolio/history?period=${period}&currency=${currency}`;
  url = withAccounts(url, accounts);
  url = withSymbols(url, symbols);
  return get<PortfolioHistory>(url);
}

export function fetchHoldings(
  currency: Currency,
  sort: HoldingSort = "value",
  order: SortOrder = "desc",
  accounts?: number[] | null,
): Promise<HoldingsResponse> {
  return get<HoldingsResponse>(withAccounts(`/api/holdings?currency=${currency}&sort=${sort}&order=${order}`, accounts));
}

export interface AccountsResponse {
  accounts: Account[];
}

export function fetchAccounts(): Promise<AccountsResponse> {
  return get<AccountsResponse>(`/api/accounts`);
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
