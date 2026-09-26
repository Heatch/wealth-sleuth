"""Portfolio valuation engine.

Computes daily portfolio values from transactions + price_history + fx_history.
All values returned in the requested display currency.
"""

import bisect
import sqlite3
from collections import defaultdict

from api.services.fx import convert, get_fx_rate_on


_ISO_DATE = "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"
# Trade date when it is a real date; otherwise settlement date. Disnat cash
# movements often have a blank trade date and a real settlement date.
_EFFECTIVE_DATE = (
    "CASE "
    f"WHEN date GLOB '{_ISO_DATE}' THEN date "
    f"WHEN settlement_date GLOB '{_ISO_DATE}' THEN settlement_date "
    "ELSE NULL END"
)


def _is_iso_date(value) -> bool:
    return bool(value) and len(value) == 10 and value[4] == "-" and value[7] == "-"


def _effective_txn_date(t):
    """Trade date, or settlement date when the trade date was not recorded."""
    trade = t["date"]
    if _is_iso_date(trade):
        return trade
    settle = t["settlement_date"] if "settlement_date" in t.keys() else None
    if _is_iso_date(settle):
        return settle
    return None


def _txn_dict(t, date):
    """Copy a transaction row onto an explicit date. sqlite3.Row is immutable."""
    return {
        "date": date,
        "type": t["type"],
        "quantity": t["quantity"],
        "net_amount": t["net_amount"],
        "currency": t["currency"],
        "security_id": t["security_id"],
        "account_id": t["account_id"],
    }


def get_date_range(conn, account_ids=None):
    """First/last dates covering transactions and prices.

    When account_ids is given, only those accounts' transactions are
    considered for the date range. Price history range is always global.
    Blank trade dates fall back to settlement date so cash contributions
    are not dropped from the window.
    """
    params = list(account_ids) if account_ids else []
    if account_ids:
        placeholders = ",".join("?" * len(account_ids))
        acct_filter = f" AND account_id IN ({placeholders})"
    else:
        acct_filter = ""
    lo = conn.execute(
        f"SELECT MIN({_EFFECTIVE_DATE}) AS dmin FROM transactions "
        f"WHERE {_EFFECTIVE_DATE} IS NOT NULL" + acct_filter,
        params,
    ).fetchone()
    first_txn = lo["dmin"] if lo else None
    hi = conn.execute(
        f"SELECT MAX({_EFFECTIVE_DATE}) AS dmax FROM transactions "
        f"WHERE {_EFFECTIVE_DATE} IS NOT NULL" + acct_filter,
        params,
    ).fetchone()
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


def load_transactions(conn, account_ids=None, security_ids=None):
    """All transactions ordered by date (undated first), optionally filtered."""
    q = "SELECT date, settlement_date, type, quantity, net_amount, currency, security_id, account_id "
    q += "FROM transactions"
    conditions = []
    params: list = []
    if account_ids:
        placeholders = ",".join("?" * len(account_ids))
        conditions.append(f"account_id IN ({placeholders})")
        params.extend(account_ids)
    if security_ids:
        placeholders = ",".join("?" * len(security_ids))
        conditions.append(f"security_id IN ({placeholders})")
        params.extend(security_ids)
    if conditions:
        q += " WHERE " + " AND ".join(conditions)
    q += " ORDER BY date, id"
    return conn.execute(q, params).fetchall()


def apply_txn(t, positions, cash):
    """Apply one txn to positions/cash. Returns external flow (deposit/withdrawal net).

    Deposits, withdrawals, and cash transfers (no security) are external
    to the account they post in. A TFSA contribution and the matching
    non-registered transfer cancel when both accounts are in the filter.
    Security journals are position movements, not cash flows.
    """
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
    elif ttype == "other" and sid is not None and net == 0:
        # Corporate action (stock split / spinoff) with no cash component:
        # add the received shares. Rows with a nonzero net_amount are cash
        # distributions (already reflected in `cash` above) whose quantity
        # column just repeats the position size, so they must not change
        # share counts.
        positions[(acct, sid)] = positions.get((acct, sid), 0.0) + qty
    if ttype in ("deposit", "withdrawal"):
        return net
    if ttype == "transfer" and sid is None and net:
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


def load_fx_index(conn):
    """Load all FX rates into sorted arrays for bisect lookup.

    Eliminates ~1,500 individual SQL queries (one per date) by loading
    once and using bisect, same pattern as price_on().
    """
    rows = conn.execute("SELECT date, rate FROM fx_history ORDER BY date").fetchall()
    dates = [r["date"] for r in rows]
    rates = [float(r["rate"]) for r in rows]
    return dates, rates


def fx_rate_on_index(fx_dates, fx_rates, d):
    """Bisect-based FX lookup. Falls back to earliest rate, then 1.0."""
    if not fx_dates:
        return 1.0
    i = bisect.bisect_right(fx_dates, d) - 1
    if i < 0:
        return fx_rates[0]
    return fx_rates[i]


def load_market_data_cached(conn):
    """Filter-independent market data, shared across all filter combinations.

    The price map, price index, and FX series depend only on price/fx
    history — not on account or security filters — so every pie-slice and
    account-filter combo reuses one copy instead of rescanning
    price_history (~0.5s) each time. All writers invalidate via
    invalidate_on_price_update(), so a stale map can never be reused.
    """
    from api.cache import cache

    key = "price_map"
    cached = cache.get(key)
    if cached is not None:
        return cached
    price_map = load_price_map(conn)
    price_index = build_price_index(price_map)
    fx_dates, fx_rates = load_fx_index(conn)
    result = (price_map, price_index, fx_dates, fx_rates)
    cache.set(key, result)
    return result


def daily_portfolio_values(conn, currency="CAD", account_ids=None, security_ids=None):
    """Daily (date, value) series plus per-date external cash flows.

    When account_ids is given, only those accounts are included.
    When security_ids is given, only those securities are valued (used for
    allocation-slice views); cash and flows are limited to transactions
    involving those securities.
    """
    currency = (currency or "CAD").upper()
    if security_ids is not None and len(security_ids) == 0:
        return [], {}, 0.0, 0.0, 0.0, {}, {}
    price_map, price_index, fx_dates, fx_rates = load_market_data_cached(conn)
    secs = load_securities(conn)
    txns = load_transactions(conn, account_ids, security_ids)
    by_date = defaultdict(list)
    undated = []
    for t in txns:
        when = _effective_txn_date(t)
        txn = _txn_dict(t, when)
        if when:
            by_date[when].append(txn)
        else:
            undated.append(txn)
    first, last = get_date_range(conn, account_ids)
    if not first or not last:
        return [], {}, 0.0, 0.0, 0.0, {}, {}
    positions = {}
    cash = {}
    # Undated external flows (e.g., Disnat contributions with Trade Date
    # "-") fund the opening balances but have no date, so they can never
    # appear in the per-date flows dict used by TWR/MWR. Track them
    # separately as the display baseline for cumulative net deposits.
    undated_by_ccy: dict[str, float] = {}
    undated_dep_by_ccy: dict[str, float] = {}
    for t in undated:
        raw_flow = apply_txn(t, positions, cash)
        ttype = t["type"]
        if security_ids is None:
            if raw_flow == 0.0:
                # Check for security transfers (DLR journals) — value at most
                # recent price for the deposits display.
                if (
                    ttype == "transfer"
                    and t["security_id"] is not None
                    and t["quantity"]
                ):
                    sid = t["security_id"]
                    dates = [d for (s, d) in price_map.keys() if s == sid]
                    if dates:
                        latest = max(dates)
                        price = price_map.get((sid, latest))
                        if price is not None:
                            sec = secs.get(sid)
                            if sec:
                                val = t["quantity"] * price
                                ccy = sec["currency"]
                                undated_dep_by_ccy[ccy] = undated_dep_by_ccy.get(ccy, 0.0) + val
                continue
            undated_by_ccy[t["currency"]] = undated_by_ccy.get(t["currency"], 0.0) + raw_flow
            undated_dep_by_ccy[t["currency"]] = undated_dep_by_ccy.get(t["currency"], 0.0) + raw_flow
        else:
            # Segment mode: undated buy/sell transactions form part of the
            # slice's cost basis for the net-deposits line.
            if ttype == "transfer":
                if t["security_id"] is not None and t["quantity"]:
                    sid = t["security_id"]
                    dates = [d for (s, d) in price_map.keys() if s == sid]
                    if dates:
                        latest = max(dates)
                        price = price_map.get((sid, latest))
                        if price is not None:
                            sec = secs.get(sid)
                            if sec:
                                val = t["quantity"] * price
                                ccy = sec["currency"]
                                undated_dep_by_ccy[ccy] = undated_dep_by_ccy.get(ccy, 0.0) + val
            elif ttype in ("buy", "sell"):
                net = t["net_amount"] or 0.0
                if net:
                    # Money put into slice securities = -net_amount.
                    undated_dep_by_ccy[t["currency"]] = undated_dep_by_ccy.get(t["currency"], 0.0) - net
    all_dates = set(by_date.keys())
    for (sid, d) in price_map.keys():
        all_dates.add(d)
    all_dates = sorted(d for d in all_dates if first <= d <= last)
    series = []
    flows = {}
    deposits = {}
    # Holding-period return of shares (and cash) already held, before today's
    # trades. New buys earn nothing today, so contributions are not performance.
    daily_returns = {}
    prev_total = None
    prev_fx = None
    prev_date = None
    for d in all_dates:
        fx_rate = fx_rate_on_index(fx_dates, fx_rates, d)
        day_txns = by_date.get(d, [])
        if prev_total is not None and prev_total > 1e-6:
            # Only securities that already had a price contribute. A holding
            # whose history starts today would otherwise book its whole value
            # as a one-day gain.
            gain = 0.0
            for (acct, sid), qty in positions.items():
                if not qty:
                    continue
                sec = secs.get(sid)
                if not sec or sec["is_cash"]:
                    continue
                price_prev = price_on(price_index, price_map, sid, prev_date)
                if price_prev is None:
                    continue
                price_today = price_on(price_index, price_map, sid, d)
                if price_today is None:
                    price_today = price_prev
                prev_val = convert(qty * price_prev, sec["currency"], currency, prev_fx)
                today_val = convert(qty * price_today, sec["currency"], currency, fx_rate)
                gain += today_val - prev_val
            if security_ids is None:
                gain += value_cash(cash, currency, fx_rate) - value_cash(cash, currency, prev_fx)
            for t in day_txns:
                if t["type"] in ("dividend", "interest", "tax"):
                    gain += convert(t["net_amount"] or 0.0, t["currency"], currency, fx_rate)
            daily_returns[d] = gain / prev_total
        else:
            daily_returns[d] = 0.0
        day_flow = 0.0
        day_dep = 0.0
        for t in day_txns:
            raw_flow = apply_txn(t, positions, cash)
            ttype = t["type"]
            if security_ids is None:
                if raw_flow != 0.0:
                    day_flow += convert(raw_flow, t["currency"], currency, fx_rate)
                    day_dep += convert(raw_flow, t["currency"], currency, fx_rate)
                elif (
                    ttype == "transfer"
                    and t["security_id"] is not None
                    and t["quantity"]
                ):
                    # Security transfer (e.g., Nobert's Gambit journal): value the
                    # shares at market price. When accounts are filtered, a
                    # transfer across accounts is real money in/out, so it must
                    # count as a cash flow for XIRR and benchmark simulation.
                    # In the all-accounts view the paired in/out legs cancel.
                    price = price_on(price_index, price_map, t["security_id"], d)
                    if price is not None:
                        sec = secs.get(t["security_id"])
                        if sec:
                            val = t["quantity"] * price
                            converted = convert(val, sec["currency"], currency, fx_rate)
                            day_flow += converted
                            day_dep += converted
            else:
                # Segment mode: the slice's cash flows for returns are the
                # signed net amounts of its transactions (buys are money put
                # into the slice, sells/dividends are money taken out).
                # Transfers are internal movements and are excluded from flows.
                if ttype == "transfer":
                    if t["security_id"] is not None and t["quantity"]:
                        price = price_on(price_index, price_map, t["security_id"], d)
                        if price is not None:
                            sec = secs.get(t["security_id"])
                            if sec:
                                val = t["quantity"] * price
                                day_dep += convert(val, sec["currency"], currency, fx_rate)
                else:
                    net = t["net_amount"] or 0.0
                    if net:
                        converted = convert(net, t["currency"], currency, fx_rate)
                        # Flip sign: a negative net_amount (buy) is money
                        # invested in the slice, so it is a positive flow.
                        day_flow -= converted
                        if ttype in ("buy", "sell"):
                            day_dep -= converted
        flows[d] = day_flow
        deposits[d] = day_dep
        total = value_positions(positions, secs, price_map, price_index, d, currency, fx_rate)
        if security_ids is None:
            total += value_cash(cash, currency, fx_rate)
        series.append((d, total))
        prev_total = total
        prev_fx = fx_rate
        prev_date = d

    # Final cash balance in display currency (for the cash totals line)
    last_fx = fx_rate_on_index(fx_dates, fx_rates, last) if all_dates else 1.0
    cash_total = value_cash(cash, currency, last_fx) if security_ids is None else 0.0
    # Undated baseline converted at the first series date's FX rate.
    # Kept OUT of `flows` so TWR/MWR math is untouched.
    first_fx = fx_rate_on_index(fx_dates, fx_rates, first) if all_dates else 1.0
    undated_base = sum(
        convert(amt, ccy, currency, first_fx)
        for ccy, amt in undated_by_ccy.items()
    )
    undated_dep_base = sum(
        convert(amt, ccy, currency, first_fx)
        for ccy, amt in undated_dep_by_ccy.items()
    )
    return series, flows, cash_total, undated_base, undated_dep_base, deposits, daily_returns


def daily_portfolio_values_cached(currency="CAD", account_ids=None, security_ids=None):
    """TTL-cached wrapper around daily_portfolio_values.

    The underlying data changes at most once per day (batch scripts),
    so a 5-minute TTL eliminates duplicate computation between the
    summary and history endpoints on page load. The cache key includes
    the sorted account and security filters so each combination is cached
    separately.
    """
    from api.cache import cache

    acct_key = tuple(sorted(account_ids)) if account_ids else "all"
    sec_key = tuple(sorted(security_ids)) if security_ids else "all"
    # v6 bump: security transfers now count as cash flows when accounts are filtered.
    key = f"valuation_v6_{currency}_{acct_key}_{sec_key}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    from database import get_connection
    conn = get_connection()
    try:
        result = daily_portfolio_values(conn, currency, account_ids, security_ids)
    finally:
        conn.close()
    cache.set(key, result)
    return result

