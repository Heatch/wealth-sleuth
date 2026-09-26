"""Portfolio API router: summary, history, holdings."""

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_db, parse_account_ids, parse_symbols, validate_currency, validate_period
from api.models import AccountsResponse, Account, HoldingsResponse, Holding, HoldingsTotals, PortfolioHistory, HistoryPoint, PortfolioSummary, PeriodReturns
from api.services import fx as fx_service
from api.services import returns as returns_service
from api.services import valuation as valuation_service

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
    conn: sqlite3.Connection = Depends(get_db),
):
    """Current value, daily change, and returns for every period."""
    try:
        cur = validate_currency(currency)
        account_ids = parse_account_ids(accounts)
        symbol_list = parse_symbols(symbols)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    security_ids = _resolve_security_ids(conn, symbol_list)
    series, _flows, cash_total, _undated, _undated_dep, _deposits, _daily_returns = valuation_service.daily_portfolio_values_cached(
        cur, account_ids, security_ids
    )
    if not series:
        raise HTTPException(status_code=404, detail="No portfolio data")
    end_value = series[-1][1]
    prev_value = series[-2][1] if len(series) >= 2 else end_value
    change = end_value - prev_value
    change_pct = (change / abs(prev_value)) if prev_value else None
    fx_rate, as_of = fx_service.get_latest_fx_rate(conn)
    returns_result = returns_service.portfolio_returns_cached(cur, account_ids, security_ids)
    raw = returns_result["periods"]
    mapped = {_period_key(k): _to_period_returns(v) for k, v in raw.items()}
    return PortfolioSummary(
        total_value=end_value,
        total_change_today=change,
        total_change_today_pct=change_pct,
        as_of_date=series[-1][0],
        fx_rate=fx_rate,
        currency=cur,
        returns=mapped,
        cash_total=None if security_ids else cash_total,
    )


@router.get("/portfolio/history", response_model=PortfolioHistory)
def get_history(
    period: str = Query("1y"),
    currency: str = Query("CAD"),
    accounts: str = Query(None),
    symbols: str = Query(None),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Time series of portfolio value for the chart."""
    try:
        per = validate_period(period)
        cur = validate_currency(currency)
        account_ids = parse_account_ids(accounts)
        symbol_list = parse_symbols(symbols)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    security_ids = _resolve_security_ids(conn, symbol_list)
    returns_result = returns_service.portfolio_returns_cached(cur, account_ids, security_ids)
    points_data = returns_result["history"].get(per, [])
    if not points_data:
        raise HTTPException(status_code=404, detail="No portfolio data")
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
    if sort not in ("value", "gain", "gain_pct", "book_cost", "symbol", "weight", "name", "shares", "country", "sector", "industry"):
        raise HTTPException(status_code=400, detail="Invalid sort field")
    if order not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="Invalid order")
    reverse = order == "desc"

    fx_rate, _ = fx_service.get_latest_fx_rate(conn)
    query = (
        "SELECT h.quantity, h.avg_cost, h.total_cost_basis, "
        "s.symbol, COALESCE(s.description, s.name) AS name, s.currency, s.asset_class, "
        "s.sector, s.industry, s.country, s.last_price, "
        "b.name AS brokerage, a.account_type "
        "FROM holdings h "
        "JOIN accounts a ON h.account_id = a.id "
        "JOIN brokerages b ON a.brokerage_id = b.id "
        "JOIN securities s ON h.security_id = s.id "
        "WHERE (s.is_cash = 0 OR s.is_cash IS NULL)"
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

