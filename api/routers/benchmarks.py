"""Benchmark API router: list available indices and fetch simulated history."""

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_db, parse_account_ids, parse_symbols, validate_currency, validate_period, validate_year
from api.models import PeriodReturns
from api.routers.portfolio import _resolve_security_ids
from api.services import benchmarks as benchmark_service

router = APIRouter()


@router.get("/benchmarks")
def get_benchmarks(
    conn: sqlite3.Connection = Depends(get_db),
):
    """List available benchmark indices."""
    return {"benchmarks": benchmark_service.list_benchmarks(conn)}


@router.get("/benchmarks/history")
def get_benchmark_history(
    benchmarks: str = Query(...),
    period: str = Query("all"),
    currency: str = Query("CAD"),
    accounts: Optional[str] = Query(None),
    symbols: Optional[str] = Query(None),
    year: Optional[str] = Query(None),
    conn: sqlite3.Connection = Depends(get_db),
):
    """Simulated benchmark history using the portfolio's actual cash flows.

    *benchmarks* is a comma-separated list of symbols (SPY, XIU.TO, QQQ).
    Account/symbol filters are applied to the cash flows exactly as they are
    for the portfolio, so the comparison stays apples-to-apples.
    """
    try:
        per = validate_period(period)
        cur = validate_currency(currency)
        account_ids = parse_account_ids(accounts)
        symbol_list = parse_symbols(symbols)
        yr = validate_year(year)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    security_ids = _resolve_security_ids(conn, symbol_list)
    requested = [s.strip().upper() for s in benchmarks.split(",") if s.strip()]
    if not requested:
        raise HTTPException(status_code=400, detail="benchmarks required")

    result = {}
    for symbol in requested:
        try:
            bench = benchmark_service.simulate_benchmark(
                symbol, cur, account_ids, security_ids, period=per, year=yr
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Simulation is already limited to the requested period or year.
        # Do not slice an all-time path; that would keep inception returns
        # and a starting value that does not match the portfolio.
        points = bench["series"]

        result[symbol] = {
            "symbol": bench["symbol"],
            "display": bench["display"],
            "series": points,
            "period_start_value": points[0]["value"] if points else None,
            "period_end_value": points[-1]["value"] if points else None,
            "returns": {k: PeriodReturns(**v) for k, v in bench["returns"].items()},
        }

    return {"benchmarks": result, "currency": cur}
