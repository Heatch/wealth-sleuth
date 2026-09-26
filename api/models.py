"""Pydantic response models for the Portfolio Tracker API."""

from typing import Optional

from pydantic import BaseModel


class PeriodReturns(BaseModel):
    twr: Optional[float] = None
    xirr: Optional[float] = None


class ReturnsMap(BaseModel):
    m1: PeriodReturns = PeriodReturns()
    m6: PeriodReturns = PeriodReturns()
    ytd: PeriodReturns = PeriodReturns()
    y1: PeriodReturns = PeriodReturns()
    y3: PeriodReturns = PeriodReturns()
    all: PeriodReturns = PeriodReturns()

    class Config:
        populate_by_name = True


class PortfolioSummary(BaseModel):
    total_value: float
    total_change_today: Optional[float] = None
    total_change_today_pct: Optional[float] = None
    as_of_date: str
    fx_rate: float
    currency: str
    returns: dict[str, PeriodReturns]
    cash_total: Optional[float] = None


class HistoryPoint(BaseModel):
    date: str
    value: float
    net_deposits: Optional[float] = None
    return_xirr: Optional[float] = None
    return_twr: Optional[float] = None


class PortfolioHistory(BaseModel):
    series: list[HistoryPoint]
    period_start_value: Optional[float] = None
    period_end_value: Optional[float] = None
    currency: str


class Holding(BaseModel):
    symbol: str
    name: str
    brokerage: str
    account_type: str
    asset_class: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    currency: str
    quantity: float
    avg_cost: float
    book_cost: float
    current_price: Optional[float] = None
    current_value: Optional[float] = None
    market_cap: Optional[float] = None
    trailing_pe: Optional[float] = None
    dividend_yield: Optional[float] = None
    gain: Optional[float] = None
    gain_pct: Optional[float] = None
    weight: Optional[float] = None
    day_change: Optional[float] = None
    day_change_pct: Optional[float] = None


class HoldingsTotals(BaseModel):
    book_cost: float
    current_value: float
    gain: float
    gain_pct: Optional[float] = None


class HoldingsResponse(BaseModel):
    holdings: list[Holding]
    totals: HoldingsTotals
    currency: str


class Account(BaseModel):
    id: int
    brokerage: str
    account_type: str
    currency: str
    txn_count: int
    holding_count: int
    has_holdings: bool


class AccountsResponse(BaseModel):
    accounts: list[Account]


class SecurityDetail(BaseModel):
    """Full company/security info shown in the expanded company card."""

    symbol: str
    name: Optional[str] = None
    description: Optional[str] = None
    currency: str
    asset_class: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    exchange: Optional[str] = None
    last_price: Optional[float] = None
    last_price_date: Optional[str] = None
    market_cap: Optional[float] = None
    trailing_pe: Optional[float] = None
    forward_pe: Optional[float] = None
    dividend_yield: Optional[float] = None
    dividend_rate: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    beta: Optional[float] = None
    eps: Optional[float] = None
    price_to_book: Optional[float] = None
    price_to_sales: Optional[float] = None
    profit_margin: Optional[float] = None
    payout_ratio: Optional[float] = None
    ex_dividend_date: Optional[str] = None
    dividend_date: Optional[str] = None
    average_volume: Optional[int] = None
    volume: Optional[int] = None
    source: str = "db"


class SecurityHistoryPoint(BaseModel):
    date: str
    close: float


class SecurityHistory(BaseModel):
    symbol: str
    currency: Optional[str] = None
    period: str
    series: list[SecurityHistoryPoint]

