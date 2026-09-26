"""Portfolio API router: summary, history, holdings."""

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_db, parse_account_ids, parse_symbols, validate_currency, validate_period, validate_year
from api.models import (
    AccountsResponse,
    Account,
    HoldingsResponse,
    Holding,
    HoldingsTotals,
    PortfolioHistory,
    HistoryPoint,
    PortfolioSummary,
    PeriodReturns,
    Record,
    RecordsResponse,
    SecurityDetail,
    SecurityHistory,
    SecurityHistoryPoint,
    TfsaSummary,
)
from api.services import fx as fx_service
from api.services import returns as returns_service
from api.services import valuation as valuation_service
from api.services import security_info
from api.services import tfsa as tfsa_service
from api.services import records as records_service

router = APIRouter()


def _period_key(period: str) -> str:
    return {"1m": "m1", "6m": "m6", "ytd": "ytd", "1y": "y1", "3y": "y3", "all": "all"}[period]


def _to_period_returns(d: dict) -> PeriodReturns:
    return PeriodReturns(twr=d.get("twr"), xirr=d.get("xirr"))


def _resolve_security_ids(conn: sqlite3.Connection, symbols: Optional[list[str]]) -> Optional[list[int]]:
    """Map canonical symbols to internal security IDs."""
    if not symbols:
        return None
    placeholders = ",".join("?" * len(symbols))
    rows = conn.execute(
        f"SELECT id FROM securities WHERE UPPER(symbol) IN ({placeholders})",
        symbols,
    ).fetchall()
    return [r["id"] for r in rows]


@router.get("/accounts", response_model=AccountsResponse)
def get_accounts(
    conn: sqlite3.Connection = Depends(get_db),
):
    """List all known accounts with holding/transaction counts."""
    rows = conn.execute(
        "SELECT a.id, b.name AS brokerage, a.account_type, a.currency, "
        "(SELECT COUNT(*) FROM transactions t WHERE t.account_id = a.id) AS txn_count, "
        "(SELECT COUNT(*) FROM holdings h WHERE h.account_id = a.id) AS holding_count "
        "FROM accounts a "
        "JOIN brokerages b ON a.brokerage_id = b.id "
        "ORDER BY b.name, a.account_type, a.currency"
    ).fetchall()
    return AccountsResponse(
        accounts=[
            Account(
                id=r["id"],
                brokerage=r["brokerage"],
                account_type=r["account_type"],
                currency=r["currency"],
                txn_count=r["txn_count"],
                holding_count=r["holding_count"],
                has_holdings=r["holding_count"] > 0,
            )
            for r in rows
        ]
    )


@router.get("/portfolio/summary", response_model=PortfolioSummary)
def get_summary(
    currency: str = Query("CAD"),
    accounts: str = Query(None),
    symbols: str = Query(None),
    year: Optional[str] = Query(None),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Current value, daily change, and returns for every period.

    If *year* is provided, the snapshot is taken at the last trading day of
    that year and the return displayed is for the full calendar year.
    """
    try:
        cur = validate_currency(currency)
        account_ids = parse_account_ids(accounts)
        symbol_list = parse_symbols(symbols)
        yr = validate_year(year)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    security_ids = _resolve_security_ids(conn, symbol_list)
    series, flows, cash_total, _undated, undated_dep, deposits, daily_returns = valuation_service.daily_portfolio_values_cached(
        cur, account_ids, security_ids
    )
    if not series:
        raise HTTPException(status_code=404, detail="No portfolio data")

    if yr:
        end_bound = f"{yr}-12-31"
        year_series = [(d, v) for d, v in series if d <= end_bound]
        if len(year_series) < 2:
            raise HTTPException(status_code=404, detail=f"No data for {yr}")
        end_value = year_series[-1][1]
        prev_value = year_series[-2][1]
        change = end_value - prev_value
        change_pct = (change / abs(prev_value)) if prev_value else None
        as_of = year_series[-1][0]
        per, _hist = returns_service.returns_for_range(
            series, flows, deposits, undated_dep,
            f"{yr}-01-01", end_bound,
            segment_mode=security_ids is not None,
            daily_returns=daily_returns,
        )
        mapped = {"m1": PeriodReturns(), "m6": PeriodReturns(), "ytd": PeriodReturns(),
                  "y1": PeriodReturns(), "y3": PeriodReturns(), "all": PeriodReturns(**per)}
    else:
        end_value = series[-1][1]
        prev_value = series[-2][1] if len(series) >= 2 else end_value
        change = end_value - prev_value
        change_pct = (change / abs(prev_value)) if prev_value else None
        as_of = series[-1][0]
        returns_result = returns_service.portfolio_returns_cached(cur, account_ids, security_ids)
        raw = returns_result["periods"]
        mapped = {_period_key(k): _to_period_returns(v) for k, v in raw.items()}

    fx_rate, _ = fx_service.get_latest_fx_rate(conn)
    return PortfolioSummary(
        total_value=end_value,
        total_change_today=change,
        total_change_today_pct=change_pct,
        as_of_date=as_of,
        fx_rate=fx_rate,
        currency=cur,
        returns=mapped,
        cash_total=None if security_ids or yr else cash_total,
    )


@router.get("/portfolio/history", response_model=PortfolioHistory)
def get_history(
    period: str = Query("1y"),
    currency: str = Query("CAD"),
    accounts: str = Query(None),
    symbols: str = Query(None),
    year: Optional[str] = Query(None),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Time series of portfolio value for the chart."""
    try:
        per = validate_period(period)
        cur = validate_currency(currency)
        account_ids = parse_account_ids(accounts)
        symbol_list = parse_symbols(symbols)
        yr = validate_year(year)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    security_ids = _resolve_security_ids(conn, symbol_list)

    if yr:
        series, flows, _cash, _undated, undated_dep, deposits, daily_returns = valuation_service.daily_portfolio_values_cached(
            cur, account_ids, security_ids
        )
        if not series:
            raise HTTPException(status_code=404, detail="No portfolio data")
        per_data, hist = returns_service.returns_for_range(
            series, flows, deposits, undated_dep,
            f"{yr}-01-01", f"{yr}-12-31",
            segment_mode=security_ids is not None,
            daily_returns=daily_returns,
        )
        points_data = hist
    else:
        returns_result = returns_service.portfolio_returns_cached(cur, account_ids, security_ids)
        points_data = returns_result["history"].get(per, [])

    if not points_data:
        raise HTTPException(status_code=404, detail="No portfolio data")

    # Full series is needed to offer the year filter even when a specific
    # period or year is currently selected.
    full_series, _flows2, _c2, _u2, _ud2, _d2, _dr2 = valuation_service.daily_portfolio_values_cached(
        cur, account_ids, security_ids
    )
    available_years = sorted({
        int(d[:4]) for d, _ in full_series if d and len(d) >= 4
    })

    points = [
        HistoryPoint(
            date=p["date"],
            value=p["value"],
            net_deposits=p["net_deposits"],
            return_xirr=p["return_xirr"],
            return_twr=p["return_twr"],
        )
        for p in points_data
    ]
    return PortfolioHistory(
        series=points,
        period_start_value=points[0].value if points else None,
        period_end_value=points[-1].value if points else None,
        currency=cur,
        available_years=available_years,
    )


@router.get("/holdings", response_model=HoldingsResponse)
def get_holdings(
    currency: str = Query("CAD"),
    sort: str = Query("value"),
    order: str = Query("desc"),
    accounts: str = Query(None),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Current holdings with live prices and gain/loss."""
    try:
        cur = validate_currency(currency)
        account_ids = parse_account_ids(accounts)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if sort not in (
        "value", "gain", "gain_pct", "book_cost", "symbol", "weight",
        "name", "shares", "country", "sector", "industry", "last_price",
        "market_cap", "trailing_pe", "dividend_yield",
    ):
        raise HTTPException(status_code=400, detail="Invalid sort field")
    if order not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="Invalid order")
    reverse = order == "desc"

    fx_rate, _ = fx_service.get_latest_fx_rate(conn)
    query = (
        "SELECT h.quantity, h.avg_cost, h.total_cost_basis, "
        "s.symbol, COALESCE(s.description, s.name) AS name, s.currency, s.asset_class, "
        "s.sector, s.industry, s.country, s.last_price, "
        "s.market_cap, s.trailing_pe, s.dividend_yield, "
        "b.name AS brokerage, a.account_type "
        "FROM holdings h "
        "JOIN accounts a ON h.account_id = a.id "
        "JOIN brokerages b ON a.brokerage_id = b.id "
        "JOIN securities s ON h.security_id = s.id "
        "WHERE (s.is_cash = 0 OR s.is_cash IS NULL) AND (s.is_benchmark = 0 OR s.is_benchmark IS NULL)"
    )
    params: list = []
    if account_ids:
        placeholders = ",".join("?" * len(account_ids))
        query += f" AND a.id IN ({placeholders})"
        params = list(account_ids)
    rows = conn.execute(query, params).fetchall()

    holdings = []
    for r in rows:
        qty = r["quantity"] or 0.0
        book = fx_service.convert(r["total_cost_basis"] or 0.0, r["currency"], cur, fx_rate)
        avg = fx_service.convert(r["avg_cost"] or 0.0, r["currency"], cur, fx_rate)
        price = r["last_price"]
        value = None
        if price is not None:
            value = fx_service.convert(qty * price, r["currency"], cur, fx_rate)
        gain = (value - book) if value is not None else None
        gain_pct = (gain / abs(book)) if gain is not None and book else None
        holdings.append(Holding(
            symbol=r["symbol"],
            name=r["name"] or r["symbol"],
            brokerage=r["brokerage"],
            account_type=r["account_type"],
            asset_class=r["asset_class"],
            sector=r["sector"],
            industry=r["industry"],
            country=r["country"],
            currency=r["currency"],
            quantity=qty,
            avg_cost=avg,
            book_cost=book,
            current_price=price,
            current_value=value,
            market_cap=r["market_cap"],
            trailing_pe=r["trailing_pe"],
            dividend_yield=r["dividend_yield"],
            gain=gain,
            gain_pct=gain_pct,
            weight=None,
            day_change=None,
            day_change_pct=None,
        ))

    total_value = sum(h.current_value or 0 for h in holdings)
    for h in holdings:
        if total_value and h.current_value is not None:
            h.weight = h.current_value / abs(total_value)

    key_map = {
        "value": lambda h: (h.current_value is None, h.current_value or 0),
        "gain": lambda h: (h.gain is None, h.gain or 0),
        "gain_pct": lambda h: (h.gain_pct is None, h.gain_pct or 0),
        "book_cost": lambda h: h.book_cost,
        "symbol": lambda h: h.symbol,
        "weight": lambda h: (h.weight is None, h.weight or 0),
        "name": lambda h: (h.name or "").lower(),
        "shares": lambda h: h.quantity,
        "country": lambda h: (h.country is None, h.country or ""),
        "sector": lambda h: (h.sector is None, h.sector or ""),
        "industry": lambda h: (h.industry is None, h.industry or ""),
        "last_price": lambda h: (h.current_price is None, h.current_price or 0),
        "market_cap": lambda h: (h.market_cap is None, h.market_cap or 0),
        "trailing_pe": lambda h: (h.trailing_pe is None, h.trailing_pe or 0),
        "dividend_yield": lambda h: (h.dividend_yield is None, h.dividend_yield or 0),
    }
    holdings.sort(key=key_map[sort], reverse=reverse)

    total_book = sum(h.book_cost for h in holdings)
    total_gain = (total_value - total_book) if holdings else 0.0
    total_gain_pct = (total_gain / abs(total_book)) if total_book else None
    totals = HoldingsTotals(
        book_cost=total_book,
        current_value=total_value,
        gain=total_gain,
        gain_pct=total_gain_pct,
    )
    return HoldingsResponse(holdings=holdings, totals=totals, currency=cur)


@router.get("/securities/{symbol}", response_model=SecurityDetail)
def get_security_detail(
    symbol: str,
    conn: sqlite3.Connection = Depends(get_db),
):
    """Full company info for the expanded company card."""
    try:
        data = security_info.get_security_detail(symbol)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load security detail: {e}")
    return SecurityDetail(**data)


@router.get("/securities/{symbol}/history", response_model=SecurityHistory)
def get_security_history(
    symbol: str,
    period: str = Query("1y"),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Historical closes for a single security chart."""
    try:
        per = validate_period(period)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        data = security_info.get_security_history(symbol, per)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load security history: {e}")
    return SecurityHistory(
        symbol=data["symbol"],
        currency=data["currency"],
        period=data["period"],
        series=[SecurityHistoryPoint(**p) for p in data["series"]],
    )


@router.get("/tfsa", response_model=TfsaSummary)
def get_tfsa_summary(
    birth_year: int = Query(2005, ge=1900, le=2100),
    accounts: str = Query(None),
    conn: sqlite3.Connection = Depends(get_db),
):
    """TFSA lifetime contributions and remaining room.

    When the frontend filters to TFSA account(s), pass the selected account
    IDs to compute room only for those accounts.
    """
    try:
        account_ids = parse_account_ids(accounts)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    data = tfsa_service.tfsa_summary(conn, birth_year=birth_year, account_ids=account_ids)
    return TfsaSummary(**data)


@router.get("/records", response_model=RecordsResponse)
def get_records(
    sort: str = Query("pct"),
    conn: sqlite3.Connection = Depends(get_db),
):
    """All-time best and worst performers across all accounts.

    Mixed realized (closed) and unrealized (open) positions. Not affected by
    account/symbol filters elsewhere on the page.
    """
    if sort not in ("pct", "amount"):
        raise HTTPException(status_code=400, detail="sort must be 'pct' or 'amount'")
    data = records_service.top_records(conn, sort_by=sort, top_n=10)
    return RecordsResponse(
        best=[Record(**r) for r in data["best"]],
        worst=[Record(**r) for r in data["worst"]],
        sort_by=data["sort_by"],
    )


@router.get("/status")
def get_status(
    conn: sqlite3.Connection = Depends(get_db),
):
    """Return data freshness status (price gaps, background fetch progress)."""
    from api.services.price_gaps import detect_price_gaps, has_gaps

    gaps = detect_price_gaps(conn)
    return {
        "gaps": {
            "missing": gaps["missing"],
            "stale": [{"id": sid, "last_date": d} for sid, d in gaps["stale"]],
            "fx_stale": gaps["fx_stale"],
            "today": gaps["today"],
        },
        "has_gaps": has_gaps(gaps),
    }


@router.post("/cache/clear")
def clear_cache():
    """Manually invalidate all API caches."""
    from api.cache import cache

    cache.invalidate()
    return {"status": "cleared"}

