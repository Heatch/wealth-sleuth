"""Pydantic response models for the Portfolio Tracker API."""

from typing import Optional

from pydantic import BaseModel


class PeriodReturns(BaseModel):
    twr: Optional[float] = None
    mwr: Optional[float] = None
    naive: Optional[float] = None


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


class HistoryPoint(BaseModel):
    date: str
    value: float


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
    currency: str
    quantity: float
    avg_cost: float
    book_cost: float
    current_price: Optional[float] = None
    current_value: Optional[float] = None
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

