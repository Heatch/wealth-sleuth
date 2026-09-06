// TypeScript interfaces matching FastAPI Pydantic models (api/models.py).

export type Currency = "CAD" | "USD";
export type Period = "1m" | "6m" | "ytd" | "1y" | "3y" | "all";
export type ReturnMethod = "twr" | "mwr" | "naive";
export type HoldingSort = "value" | "gain" | "gain_pct" | "book_cost" | "symbol" | "weight";
export type SortOrder = "asc" | "desc";

export interface PeriodReturns {
  twr: number | null;
  mwr: number | null;
  naive: number | null;
}

export interface PortfolioSummary {
  total_value: number;
  total_change_today: number | null;
  total_change_today_pct: number | null;
  as_of_date: string;
  fx_rate: number;
  currency: string;
  returns: Record<string, PeriodReturns>;
}

export interface HistoryPoint {
  date: string;
  value: number;
}

export interface PortfolioHistory {
  series: HistoryPoint[];
  period_start_value: number | null;
  period_end_value: number | null;
  currency: string;
}

export interface Holding {
  symbol: string;
  name: string;
  brokerage: string;
  account_type: string;
  asset_class: string | null;
  currency: string;
  quantity: number;
  avg_cost: number;
  book_cost: number;
  current_price: number | null;
  current_value: number | null;
  gain: number | null;
  gain_pct: number | null;
  weight: number | null;
  day_change: number | null;
  day_change_pct: number | null;
}

export interface HoldingsTotals {
  book_cost: number;
  current_value: number;
  gain: number;
  gain_pct: number | null;
}

export interface HoldingsResponse {
  holdings: Holding[];
  totals: HoldingsTotals;
  currency: string;
}

