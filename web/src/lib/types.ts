// TypeScript interfaces matching FastAPI Pydantic models (api/models.py).

export type Currency = "CAD" | "USD";
export type Period = "1m" | "6m" | "ytd" | "1y" | "3y" | "all";
export type ReturnMethod = "twr" | "xirr";
export type HoldingSort =
  | "value"
  | "gain"
  | "gain_pct"
  | "book_cost"
  | "symbol"
  | "weight"
  | "name"
  | "shares"
  | "country"
  | "sector"
  | "industry"
  | "last_price"
  | "market_cap"
  | "trailing_pe"
  | "dividend_yield";
export type SortOrder = "asc" | "desc";
export type AllocationDimension = "sector" | "country";
export interface AllocationFilter {
  dimension: AllocationDimension;
  value: string;
}

export interface PeriodReturns {
  twr: number | null;
  xirr: number | null;
}

export interface PortfolioSummary {
  total_value: number;
  total_change_today: number | null;
  total_change_today_pct: number | null;
  as_of_date: string;
  fx_rate: number;
  currency: string;
  returns: Record<string, PeriodReturns>;
  cash_total?: number | null;
}

export interface HistoryPoint {
  date: string;
  value: number;
  net_deposits?: number | null;
  return_xirr?: number | null;
  return_twr?: number | null;
}

export interface PortfolioHistory {
  series: HistoryPoint[];
  period_start_value: number | null;
  period_end_value: number | null;
  currency: string;
  available_years: number[];
}

export interface Benchmark {
  symbol: string;
  name: string;
  currency: string;
}

export interface BenchmarkHistory {
  symbol: string;
  display: string;
  series: HistoryPoint[];
  period_start_value: number | null;
  period_end_value: number | null;
  returns: Record<string, PeriodReturns>;
}

export interface BenchmarksHistoryResponse {
  benchmarks: Record<string, BenchmarkHistory>;
  currency: string;
}

export interface Holding {
  symbol: string;
  name: string;
  brokerage: string;
  account_type: string;
  asset_class: string | null;
  sector: string | null;
  industry: string | null;
  country: string | null;
  currency: string;
  quantity: number;
  avg_cost: number;
  book_cost: number;
  current_price: number | null;
  current_value: number | null;
  market_cap: number | null;
  trailing_pe: number | null;
  dividend_yield: number | null;
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

export interface SecurityDetail {
  symbol: string;
  name: string | null;
  description: string | null;
  currency: string;
  asset_class: string | null;
  sector: string | null;
  industry: string | null;
  country: string | null;
  exchange: string | null;
  last_price: number | null;
  last_price_date: string | null;
  market_cap: number | null;
  trailing_pe: number | null;
  forward_pe: number | null;
  dividend_yield: number | null;
  dividend_rate: number | null;
  fifty_two_week_high: number | null;
  fifty_two_week_low: number | null;
  beta: number | null;
  eps: number | null;
  price_to_book: number | null;
  price_to_sales: number | null;
  profit_margin: number | null;
  payout_ratio: number | null;
  ex_dividend_date: string | null;
  dividend_date: string | null;
  average_volume: number | null;
  volume: number | null;
  source: string;
}

export interface SecurityHistoryPoint {
  date: string;
  close: number;
}

export interface SecurityHistory {
  symbol: string;
  currency: string | null;
  period: string;
  series: SecurityHistoryPoint[];
}

export interface TfsaSummary {
  birth_year: number;
  year_turned_18: number;
  first_contribution_year: number;
  current_year: number;
  lifetime_contributions: number;
  lifetime_withdrawals: number;
  cumulative_room: number;
  withdrawal_room: number;
  total_room: number;
  remaining_room: number;
  pct_used: number;
}

export interface TradeRecord {
  account_id: number;
  brokerage: string;
  account_type: string;
  security_id: number;
  symbol: string;
  name: string | null;
  currency: string;
  sector: string | null;
  country: string | null;
  is_open: boolean;
  buy_date: string;
  sell_date: string | null;
  quantity: number;
  buy_price: number;
  sell_price: number | null;
  cost_basis: number;
  proceeds_or_value: number;
  gain_amount: number;
  gain_pct: number;
  gain_amount_cad: number;
  gain_pct_cad: number;
  duration_days: number;
  duration_label: string;
}

export interface RecordsResponse {
  best: TradeRecord[];
  worst: TradeRecord[];
  sort_by: string;
}

export interface Account {
  id: number;
  brokerage: string;
  account_type: string;
  currency: string;
  txn_count: number;
  holding_count: number;
  has_holdings: boolean;
}
