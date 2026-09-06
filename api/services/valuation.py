"""Portfolio valuation engine.

Computes daily portfolio values from transactions + price_history + fx_history.
All values returned in the requested display currency.
"""

import bisect
import sqlite3
from collections import defaultdict

from api.services.fx import convert, get_fx_rate_on


def get_date_range(conn):
    """First/last dates covering transactions and prices."""
    # Only real YYYY-MM-DD dates (never CSV footers like "As of ...")
    valid = "date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'"
    lo = conn.execute("SELECT MIN(date) AS dmin FROM transactions WHERE " + valid).fetchone()
    first_txn = lo["dmin"] if lo else None
    hi = conn.execute("SELECT MAX(date) AS dmax FROM transactions WHERE " + valid).fetchone()
    last_txn = hi["dmax"] if hi else None
    lp = conn.execute("SELECT MAX(date) AS dmax FROM price_history").fetchone()
    last_price = lp["dmax"] if lp else None
    last_date = last_txn
    if last_price and (not last_date or last_price > last_date):
        last_date = last_price
    return first_txn, last_date


def load_price_map(conn):
    """Map of (security_id, date) -> close_price."""
    price_map = {}
    q = "SELECT security_id, date, close_price FROM price_history"
    for r in conn.execute(q).fetchall():
        price_map[(r["security_id"], r["date"])] = float(r["close_price"])
    return price_map


def load_securities(conn):
    """Map of security_id -> {symbol, currency, is_cash}."""
    secs = {}
    q = "SELECT id, symbol, currency, is_cash FROM securities"
    for r in conn.execute(q).fetchall():
        secs[r["id"]] = {"symbol": r["symbol"], "currency": r["currency"], "is_cash": bool(r["is_cash"])}
    return secs


def load_transactions(conn):
    """All transactions ordered by date (undated first)."""
    q = "SELECT date, type, quantity, net_amount, currency, security_id, account_id "
    q += "FROM transactions ORDER BY date, id"
    return conn.execute(q).fetchall()


def apply_txn(t, positions, cash):
    """Apply one txn to positions/cash. Returns external flow (deposit/withdrawal net)."""
    ttype = t["type"]
    qty = t["quantity"] or 0.0
    net = t["net_amount"] or 0.0
    ccy = t["currency"]
    acct = t["account_id"]
    sid = t["security_id"]
    cash[(acct, ccy)] = cash.get((acct, ccy), 0.0) + net
    if ttype == "buy" and sid is not None:
        positions[(acct, sid)] = positions.get((acct, sid), 0.0) + abs(qty)
    elif ttype == "sell" and sid is not None:
        positions[(acct, sid)] = positions.get((acct, sid), 0.0) - abs(qty)
    elif ttype == "transfer" and sid is not None:
        positions[(acct, sid)] = positions.get((acct, sid), 0.0) + qty
    if ttype == "deposit":
        return net
    if ttype == "withdrawal":
        return net
    return 0.0


def build_price_index(price_map):
    # {sid: sorted date list} for bisect-based latest-price lookup.
    # Unlike an incremental cache, this prices a security correctly
    # even if first bought AFTER its price history ends (e.g. GOOG
    # bought 2026-07-31, .NE history ends 2026-07-17).
    index = {}
    for (sid, d) in price_map.keys():
        index.setdefault(sid, []).append(d)
    for dates in index.values():
        dates.sort()
    return index


def price_on(price_index, price_map, sid, d):
    # Latest close at or before d. Returns None if none exists.
    dates = price_index.get(sid)
    if not dates:
        return None
    i = bisect.bisect_right(dates, d) - 1
    if i < 0:
        return None
    return price_map[(sid, dates[i])]


def value_positions(positions, secs, price_map, price_index, d, currency, fx_rate):
    """Value security positions on date d in display currency."""
    total = 0.0
    for (acct, sid), qty in positions.items():
        if not qty:
            continue
        sec = secs.get(sid)
        if not sec or sec["is_cash"]:
            continue
        price = price_on(price_index, price_map, sid, d)
        if price is None:
            continue
        total += convert(qty * price, sec["currency"], currency, fx_rate)
    return total


def value_cash(cash, currency, fx_rate):
    """Value cash balances on date d in display currency."""
    total = 0.0
    for (acct, ccy), bal in cash.items():
        if not bal:
            continue
        total += convert(bal, ccy, currency, fx_rate)
    return total


def daily_portfolio_values(conn, currency="CAD"):
    """Daily (date, value) series plus per-date external cash flows."""
    currency = (currency or "CAD").upper()
    price_map = load_price_map(conn)
    secs = load_securities(conn)
    txns = load_transactions(conn)
    by_date = defaultdict(list)
    undated = []
    for t in txns:
        if t["date"]:
            by_date[t["date"]].append(t)
        else:
            undated.append(t)
    first, last = get_date_range(conn)
    if not first or not last:
        return [], {}
    positions = {}
    cash = {}
    for t in undated:
        apply_txn(t, positions, cash)
    all_dates = set(by_date.keys())
    for (sid, d) in price_map.keys():
        all_dates.add(d)
    all_dates = sorted(d for d in all_dates if first <= d <= last)
    price_index = build_price_index(price_map)
    series = []
    flows = {}
    for d in all_dates:
        day_flow = 0.0
        for t in by_date.get(d, []):
            day_flow += apply_txn(t, positions, cash)
        flows[d] = day_flow
        fx_rate = get_fx_rate_on(conn, d)
        total = value_positions(positions, secs, price_map, price_index, d, currency, fx_rate)
        total += value_cash(cash, currency, fx_rate)
        series.append((d, total))
    return series, flows

