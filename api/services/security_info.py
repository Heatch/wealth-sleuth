"""Security detail + history helpers with smart caching.

The goal is to serve the company card (expanded row) quickly while still
surfacing richer yfinance fields (beta, EPS, valuation ratios, etc.).

Caching strategy
- Security detail: 5 min TTL.  Prices change at most every 15 min via the
  live-price loop; static fundamentals change daily.
- Raw yfinance info: 5 min TTL.  Avoids repeated Yahoo calls when the user
  toggles between the same few rows.
- Security price history: 5 min TTL.  Historical closes are batch-updated
  once per day.
"""

import sqlite3
from datetime import date, timedelta
from typing import Optional

from config import DB_PATH
from database import get_connection


def _today() -> str:
    return date.today().isoformat()


def _is_stale(last_date: Optional[str], max_age_days: int = 1) -> bool:
    if not last_date:
        return True
    try:
        d = date.fromisoformat(last_date)
    except Exception:
        return True
    return (date.today() - d).days > max_age_days


def _yf_info(symbol: str) -> Optional[dict]:
    """Fetch yfinance .info with a short internal cache."""
    from api.cache import cache

    cache_key = f"yf_info_{symbol.upper()}"
    cached = cache.get(cache_key, ttl=300)
    if cached is not None:
        return cached if cached else None

    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info
    except Exception:
        cache.set(cache_key, {})
        return None

    cache.set(cache_key, info if info else {})
    return info if info else None


def _resolve_yf_ticker(symbol: str, currency: str, is_cdr: int) -> list[str]:
    """Mirror fetch_security_info.resolve_ticker for the Yahoo lookup."""
    if currency == "USD":
        return [symbol]
    if is_cdr:
        return [f"{symbol}.NE", f"{symbol}.TO"]
    return [f"{symbol}.TO", f"{symbol}.V", f"{symbol}.CN", symbol]


def _safe_float(v):
    if v is None:
        return None
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except Exception:
        return None


def _safe_int(v):
    if v is None:
        return None
    try:
        return int(v)
    except Exception:
        return None


def _fmt_date(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, int):
        # yfinance sometimes returns epoch seconds
        try:
            return date.fromtimestamp(v).isoformat()
        except Exception:
            return None
    if isinstance(v, str):
        try:
            return date.fromisoformat(v.split("T")[0]).isoformat()
        except Exception:
            return None
    return None


def _merge_yf_detail(base: dict, info: dict) -> dict:
    """Overlay yfinance info onto DB values only when missing/stale."""
    mappings = {
        "name": "longName",
        "description": "longBusinessSummary",
        "sector": "sector",
        "industry": "industry",
        "country": "country",
        "exchange": "exchange",
        "last_price": "regularMarketPrice",
        "market_cap": "marketCap",
        "trailing_pe": "trailingPE",
        "forward_pe": "forwardPE",
        "dividend_yield": "dividendYield",
        "dividend_rate": "dividendRate",
        "fifty_two_week_high": "fiftyTwoWeekHigh",
        "fifty_two_week_low": "fiftyTwoWeekLow",
        "beta": "beta",
        "eps": "trailingEps",
        "price_to_book": "priceToBook",
        "price_to_sales": "priceToSalesTrailing12Months",
        "profit_margin": "profitMargins",
        "payout_ratio": "payoutRatio",
        "ex_dividend_date": "exDividendDate",
        "dividend_date": "dividendDate",
        "average_volume": "averageVolume",
        "volume": "volume",
    }

    out = dict(base)
    for target_key, yf_key in mappings.items():
        current = out.get(target_key)
        if current is None or current == "":
            out[target_key] = info.get(yf_key)

    # Yahoo's dividendYield is inconsistent: sometimes a decimal fraction,
    # sometimes the percentage value itself. Prefer dividendRate/price when
    # both are available, otherwise treat raw values > 1 as percentages.
    price = _safe_float(out.get("last_price"))
    div_rate = _safe_float(out.get("dividend_rate"))
    raw_yield = _safe_float(out.get("dividend_yield"))
    if div_rate is not None and price:
        out["dividend_yield"] = div_rate / price
    elif raw_yield is not None and raw_yield > 1:
        out["dividend_yield"] = raw_yield / 100.0
    else:
        out["dividend_yield"] = raw_yield

    # Coerce types
    for k in ["last_price", "market_cap", "trailing_pe", "forward_pe",
              "dividend_rate", "fifty_two_week_high",
              "fifty_two_week_low", "beta", "eps", "price_to_book",
              "price_to_sales", "profit_margin", "payout_ratio"]:
        out[k] = _safe_float(out.get(k))
    for k in ["average_volume", "volume"]:
        out[k] = _safe_int(out.get(k))
    for k in ["ex_dividend_date", "dividend_date"]:
        out[k] = _fmt_date(out.get(k))

    out["source"] = "yfinance"
    return out


def get_security_detail(symbol: str, db_path=None) -> dict:
    """Return combined DB + yfinance data for a single security. Cached."""
    from api.cache import cache

    key = f"security_detail_{symbol.upper()}"
    cached = cache.get(key, ttl=300)
    if cached is not None:
        return cached

    conn = get_connection(db_path or DB_PATH)
    try:
        row = conn.execute(
            "SELECT * FROM securities WHERE UPPER(symbol) = ?",
            (symbol.upper(),),
        ).fetchone()
        if not row:
            raise ValueError(f"Security not found: {symbol}")

        r = dict(row)
        base = {
            "symbol": r.get("symbol", symbol),
            "name": r.get("name") or r.get("description"),
            "description": r.get("description"),
            "currency": r.get("currency", "CAD"),
            "asset_class": r.get("asset_class"),
            "sector": r.get("sector"),
            "industry": r.get("industry"),
            "country": r.get("country"),
            "exchange": r.get("exchange"),
            "last_price": _safe_float(r.get("last_price")),
            "last_price_date": r.get("last_price_date"),
            "market_cap": _safe_float(r.get("market_cap")),
            "trailing_pe": _safe_float(r.get("trailing_pe")),
            "forward_pe": _safe_float(r.get("forward_pe")),
            "dividend_yield": _safe_float(r.get("dividend_yield")),
            "dividend_rate": _safe_float(r.get("dividend_rate")),
            "fifty_two_week_high": _safe_float(r.get("fifty_two_week_high")),
            "fifty_two_week_low": _safe_float(r.get("fifty_two_week_low")),
            "beta": None,
            "eps": None,
            "price_to_book": None,
            "price_to_sales": None,
            "profit_margin": None,
            "payout_ratio": None,
            "ex_dividend_date": None,
            "dividend_date": None,
            "average_volume": None,
            "volume": None,
            "source": "db",
        }

        # Decide whether to hit yfinance for enrichment.
        needs_enrich = (
            base["last_price"] is None
            or _is_stale(base["last_price_date"], max_age_days=1)
            or base["market_cap"] is None
            or base["beta"] is None
        )

        if needs_enrich:
            is_cdr = bool(r.get("is_cdr"))
            candidates = _resolve_yf_ticker(base["symbol"], base["currency"], is_cdr)
            for cand in candidates:
                info = _yf_info(cand)
                if info and (info.get("regularMarketPrice") or info.get("currentPrice")):
                    base = _merge_yf_detail(base, info)
                    break
    finally:
        conn.close()

    cache.set(key, base)
    return base


def _period_start(period: str, today: date) -> Optional[str]:
    if period == "all":
        return None
    if period == "ytd":
        return date(today.year, 1, 1).isoformat()
    if period == "1m":
        return (today - timedelta(days=30)).isoformat()
    if period == "6m":
        return (today - timedelta(days=180)).isoformat()
    if period == "1y":
        return (today - timedelta(days=365)).isoformat()
    if period == "3y":
        return (today - timedelta(days=3 * 365)).isoformat()
    return None


def get_security_history(symbol: str, period: str = "1y", db_path=None) -> dict:
    """Historical closes for a single security, cached."""
    from api.cache import cache

    key = f"security_history_{symbol.upper()}_{period}"
    cached = cache.get(key, ttl=300)
    if cached is not None:
        return cached

    conn = get_connection(db_path or DB_PATH)
    try:
        sec = conn.execute(
            "SELECT id, symbol, currency FROM securities WHERE UPPER(symbol) = ?",
            (symbol.upper(),),
        ).fetchone()
        if not sec:
            raise ValueError(f"Security not found: {symbol}")

        start = _period_start(period, date.today())
        params = [sec["id"]]
        where = "security_id = ?"
        if start:
            where += " AND date >= ?"
            params.append(start)

        rows = conn.execute(
            f"SELECT date, close_price FROM price_history WHERE {where} ORDER BY date",
            params,
        ).fetchall()

        result = {
            "symbol": sec["symbol"],
            "currency": sec["currency"],
            "period": period,
            "series": [{"date": r["date"], "close": float(r["close_price"])} for r in rows],
        }
    finally:
        conn.close()

    cache.set(key, result)
    return result
