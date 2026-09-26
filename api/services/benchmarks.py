"""Benchmark simulation: compare portfolio performance against broad indices.

Simulation is period-specific. At the start of the selected window the
benchmark is worth exactly what the portfolio is worth, as if that opening
value had been invested in the index. Later deposits and withdrawals in the
window are invested in (or taken out of) the index at that day's price.
TWR is the compounded price return of shares already held, so a new deposit
is not counted as performance. XIRR uses the opening value plus those later
cash flows.
"""

import bisect
import sqlite3
from typing import Callable, Optional

from api.services import returns as returns_service
from api.services.fx import convert
from api.services.valuation import daily_portfolio_values_cached, load_market_data_cached, fx_rate_on_index
from database import get_connection


# Canonical benchmark symbols and display labels.
BENCHMARKS = {
    "SPY": {"display": "S&P 500", "currency": "USD"},
    "XIU.TO": {"display": "TSX 60", "currency": "CAD"},
    "QQQ": {"display": "NASDAQ 100", "currency": "USD"},
}


def list_benchmarks(conn: sqlite3.Connection) -> list[dict]:
    """Return the benchmark securities currently in the database."""
    rows = conn.execute(
        "SELECT symbol, name, currency FROM securities WHERE is_benchmark = 1 ORDER BY symbol"
    ).fetchall()
    out = []
    for r in rows:
        meta = BENCHMARKS.get(r["symbol"], {})
        out.append({
            "symbol": r["symbol"],
            "name": meta.get("display", r["name"] or r["symbol"]),
            "currency": r["currency"],
        })
    return out


def _load_benchmark_price_map(conn: sqlite3.Connection, security_id: int) -> dict[str, float]:
    rows = conn.execute(
        "SELECT date, close_price FROM price_history WHERE security_id = ? ORDER BY date",
        (security_id,),
    ).fetchall()
    return {r["date"]: float(r["close_price"]) for r in rows}


def _latest_price(dates: list[str], price_map: dict[str, float], d: str) -> Optional[float]:
    i = bisect.bisect_right(dates, d) - 1
    if i < 0:
        return None
    return price_map.get(dates[i])


def simulate_index_path(
    window: list[tuple[str, float]],
    flows: dict,
    price_on: Callable[[str], Optional[float]],
) -> tuple[list[tuple[str, float]], dict[str, float], dict[str, float]]:
    """Invest *window[0]*'s portfolio value in an index, then apply later flows.

    Returns (value series, applied flows, holding-period daily returns).
    The first value equals the portfolio's opening value whenever a price
    exists. A flow on the opening date is already inside that value and is
    not applied again. Daily returns measure the price change of shares
    already held, before today's cash flow.
    """
    if not window:
        return [], {}, {}

    start_date, start_value = window[0]
    start_value = float(start_value or 0.0)
    price0 = price_on(start_date)
    if price0 is None or price0 <= 0:
        return [], {}, {}

    shares = start_value / price0 if start_value else 0.0
    series: list[tuple[str, float]] = [(start_date, start_value)]
    applied: dict[str, float] = {}
    daily: dict[str, float] = {start_date: 0.0}
    prev_value = start_value
    prev_shares = shares

    for d, _portfolio_value in window[1:]:
        price = price_on(d)
        if price is None or price <= 0:
            price = price0
        pre_flow = prev_shares * price
        if prev_value > 1e-6:
            daily[d] = (pre_flow - prev_value) / prev_value
        elif pre_flow > 1e-6 and prev_shares > 1e-12:
            daily[d] = 0.0
        else:
            daily[d] = 0.0

        flow = flows.get(d, 0.0) or 0.0
        if flow and price > 0:
            # A withdrawal cannot sell more of the index than is held.
            if flow < 0:
                applied_flow = max(flow, -(shares * price))
            else:
                applied_flow = flow
            if abs(applied_flow) > 1e-9:
                shares += applied_flow / price
                if shares < 0:
                    shares = 0.0
                applied[d] = applied_flow

        value = shares * price
        series.append((d, value))
        prev_value = value
        prev_shares = shares
        price0 = price

    return series, applied, daily


def _window_for_period(
    portfolio_series: list,
    period: str,
    year: Optional[int],
) -> list:
    """Slice the portfolio series to the same window the chart is showing."""
    if not portfolio_series:
        return []
    if year:
        start = f"{year}-01-01"
        end = f"{year}-12-31"
        return [(d, v) for d, v in portfolio_series if start <= d <= end]
    today = portfolio_series[-1][0]
    start = returns_service.period_start(period, portfolio_series, today)
    return [(d, v) for d, v in portfolio_series if d >= start]


def simulate_benchmark(
    benchmark_symbol: str,
    currency: str = "CAD",
    account_ids: Optional[list] = None,
    security_ids: Optional[list] = None,
    period: str = "all",
    year: Optional[int] = None,
) -> dict:
    """Simulate the selected period as if the portfolio had been in the index.

    The benchmark series starts at the portfolio's value on the first day of
    the period. Returns on each point are cumulative from that day, not from
    the beginning of the account.
    """
    currency = (currency or "CAD").upper()
    benchmark_symbol = benchmark_symbol.upper()
    if benchmark_symbol not in BENCHMARKS:
        raise ValueError(f"Unknown benchmark: {benchmark_symbol}")

    portfolio_result = daily_portfolio_values_cached(currency, account_ids, security_ids)
    portfolio_series, flows, _cash_total, _undated_base, _undated_dep, deposits, _daily_returns = portfolio_result
    if not portfolio_series:
        return {"series": [], "returns": {}, "period_start_value": None, "period_end_value": None}

    window = _window_for_period(portfolio_series, period, year)
    if len(window) < 2:
        return {"series": [], "returns": {}, "period_start_value": None, "period_end_value": None}

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, currency FROM securities WHERE symbol = ? AND is_benchmark = 1",
            (benchmark_symbol,),
        ).fetchone()
        if not row:
            return {"series": [], "returns": {}, "period_start_value": None, "period_end_value": None}
        bench_ccy = row["currency"]
        price_map = _load_benchmark_price_map(conn, row["id"])
        _, _, fx_dates, fx_rates = load_market_data_cached(conn)
    finally:
        conn.close()

    if not price_map:
        return {"series": [], "returns": {}, "period_start_value": None, "period_end_value": None}

    price_dates = sorted(price_map.keys())

    def price_on(d: str) -> Optional[float]:
        raw = _latest_price(price_dates, price_map, d)
        if raw is None:
            return None
        if currency == bench_ccy:
            return raw
        fx = fx_rate_on_index(fx_dates, fx_rates, d)
        return convert(raw, bench_ccy, currency, fx)

    series, applied_flows, daily_returns = simulate_index_path(window, flows, price_on)
    if len(series) < 2:
        return {"series": [], "returns": {}, "period_start_value": None, "period_end_value": None}

    per, history = returns_service.returns_for_range(
        series,
        applied_flows,
        deposits,
        0.0,
        series[0][0],
        series[-1][0],
        segment_mode=security_ids is not None,
        daily_returns=daily_returns,
    )

    return {
        "symbol": benchmark_symbol,
        "display": BENCHMARKS[benchmark_symbol]["display"],
        "series": history,
        "returns": {period if not year else "year": per},
        "period_start_value": history[0]["value"] if history else None,
        "period_end_value": history[-1]["value"] if history else None,
    }
