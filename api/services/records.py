"""All-time best/worst performer records (realized + unrealized).

Builds FIFO lots per (account, security) from transactions, handling stock
splits (corporate actions). Closed lots become realized trade records; open
lots become unrealized position records. Records are consolidated per symbol
so a position built up over multiple buys appears as a single entry.
"""

import bisect
from datetime import date
from typing import Optional

from spinoffs import spinoff_adjustments


def _load_fx_index(conn) -> tuple[list[str], list[float]]:
    rows = conn.execute("SELECT date, rate FROM fx_history ORDER BY date").fetchall()
    dates = [r["date"] for r in rows]
    rates = [float(r["rate"]) for r in rows]
    return dates, rates


def _to_cad(amount: float, currency: str, date_str: str, fx_dates: list[str], fx_rates: list[float]) -> float:
    currency = (currency or "CAD").upper()
    if currency == "CAD" or not fx_dates:
        return amount
    if not date_str:
        rate = fx_rates[-1]
        return amount * rate
    i = bisect.bisect_right(fx_dates, date_str) - 1
    if i < 0:
        i = 0
    return amount * fx_rates[i]


def _format_duration(days: int) -> str:
    if days < 0:
        days = 0
    years = days // 365
    rem = days % 365
    months = rem // 30
    rem_days = rem % 30
    parts = []
    if years:
        parts.append(f"{years}y")
    if months:
        parts.append(f"{months}m")
    if rem_days or not parts:
        parts.append(f"{rem_days}d")
    return " ".join(parts)


def _today() -> str:
    return date.today().isoformat()


def _days_between(start: str, end: str) -> int:
    try:
        d1 = date.fromisoformat(start)
        d2 = date.fromisoformat(end)
        return max(0, (d2 - d1).days)
    except Exception:
        return 0


def _consolidate(records: list[dict]) -> list[dict]:
    """Merge per-lot records of the same (symbol, is_open) into one record.

    Uses weighted-average buy/sell prices and a cost-weighted holding period.
    """
    groups: dict[tuple[str, bool], list[dict]] = {}
    for r in records:
        key = (r["symbol"], r["is_open"])
        groups.setdefault(key, []).append(r)

    result: list[dict] = []
    for (symbol, is_open), group in groups.items():
        base = group[0]
        total_qty = sum(r["quantity"] for r in group)
        total_cost_local = sum(r["cost_basis"] for r in group)
        total_cost_cad = sum(r["cost_basis_cad"] for r in group)
        total_proceeds_local = sum(r["proceeds_or_value"] for r in group)
        total_proceeds_cad = sum(r["proceeds_cad"] for r in group)

        gain_local = total_proceeds_local - total_cost_local
        gain_cad = total_proceeds_cad - total_cost_cad
        gain_pct_local = (gain_local / total_cost_local) if total_cost_local else 0.0
        gain_pct_cad = (gain_cad / total_cost_cad) if total_cost_cad else gain_pct_local

        buy_price = (total_cost_local / total_qty) if total_qty else 0.0
        sell_price = (total_proceeds_local / total_qty) if total_qty else 0.0

        buy_date = min(r["buy_date"] for r in group)
        sell_date = max(r["sell_date"] for r in group if r["sell_date"]) if not is_open else None

        # Cost-weighted holding period.
        if total_cost_cad > 1e-9:
            weighted_days = sum(r["duration_days"] * r["cost_basis_cad"] for r in group) / total_cost_cad
        else:
            weighted_days = sum(r["duration_days"] for r in group) / max(1, len(group))
        duration_days = int(round(weighted_days))

        result.append({
            "account_id": base["account_id"],
            "brokerage": base["brokerage"],
            "account_type": base["account_type"],
            "security_id": base["security_id"],
            "symbol": symbol,
            "name": base["name"],
            "currency": base["currency"],
            "sector": base["sector"],
            "country": base["country"],
            "is_open": is_open,
            "buy_date": buy_date,
            "sell_date": sell_date,
            "quantity": total_qty,
            "buy_price": buy_price,
            "sell_price": sell_price,
            "cost_basis": total_cost_local,
            "proceeds_or_value": total_proceeds_local,
            "gain_amount": gain_local,
            "gain_pct": gain_pct_local,
            "gain_amount_cad": gain_cad,
            "gain_pct_cad": gain_pct_cad,
            "cost_basis_cad": total_cost_cad,
            "proceeds_cad": total_proceeds_cad,
            "duration_days": duration_days,
            "duration_label": _format_duration(duration_days),
        })
    return result


def compute_records(conn) -> list[dict]:
    """Return consolidated all-time records (closed + open) across all accounts."""
    fx_dates, fx_rates = _load_fx_index(conn)

    secs = {
        r["id"]: dict(r)
        for r in conn.execute(
            "SELECT id, symbol, COALESCE(description, name) AS name, currency, "
            "sector, country, last_price FROM securities"
        ).fetchall()
    }

    accounts = {
        r["id"]: dict(r)
        for r in conn.execute(
            "SELECT a.id, a.account_type, b.name AS brokerage "
            "FROM accounts a JOIN brokerages b ON a.brokerage_id = b.id"
        ).fetchall()
    }

    txns = conn.execute(
        "SELECT id, account_id, security_id, date, type, quantity, net_amount, price, currency "
        "FROM transactions "
        "WHERE security_id IS NOT NULL "
        "AND type IN ('buy', 'sell', 'transfer', 'other') "
        "ORDER BY account_id, security_id, date, id"
    ).fetchall()

    grouped: dict[tuple[int, int], list[dict]] = {}
    for t in txns:
        key = (t["account_id"], t["security_id"])
        grouped.setdefault(key, []).append({
            "date": t["date"] or _today(),
            "type": t["type"],
            "quantity": float(t["quantity"] or 0),
            "net_amount": float(t["net_amount"] or 0),
            "price": float(t["price"] or 0) if t["price"] else None,
            "currency": (t["currency"] or "CAD").upper(),
        })

    records: list[dict] = []

    # Spinoff reallocations (e.g. TRP -> SOBO): part of the parent's cost
    # moves to the child, so neither leg is measured off a $0 basis.
    parent_scales, child_costs = spinoff_adjustments(conn)

    for (account_id, security_id), group_txns in grouped.items():
        sec = secs.get(security_id)
        acct = accounts.get(account_id)
        if not sec or not acct:
            continue

        lots: list[dict] = []

        # Spinoff hook state for this (account, security).
        scale_info = parent_scales.get((account_id, security_id))
        scale_applied = False
        child_info = child_costs.get((account_id, security_id))

        def add_lot(txn_date: str, qty: float, cost_per_share: float):
            if qty <= 1e-9:
                return
            lots.append({"date": txn_date, "cost_per_share": cost_per_share, "remaining_qty": qty})

        def close_lots(qty_to_close: float, close_date: str, close_price: float) -> list[dict]:
            closed: list[dict] = []
            remaining = qty_to_close
            while remaining > 1e-9 and lots:
                lot = lots[0]
                close_qty = min(remaining, lot["remaining_qty"])
                if close_qty <= 1e-9:
                    lots.pop(0)
                    continue

                cost_local = close_qty * lot["cost_per_share"]
                proceeds_local = close_qty * close_price
                gain_local = proceeds_local - cost_local

                cost_cad = _to_cad(cost_local, sec["currency"], lot["date"], fx_dates, fx_rates)
                proceeds_cad = _to_cad(proceeds_local, sec["currency"], close_date, fx_dates, fx_rates)

                days = _days_between(lot["date"], close_date)

                closed.append({
                    "account_id": account_id,
                    "brokerage": acct["brokerage"],
                    "account_type": acct["account_type"],
                    "security_id": security_id,
                    "symbol": sec["symbol"],
                    "name": sec["name"],
                    "currency": sec["currency"],
                    "sector": sec["sector"],
                    "country": sec["country"],
                    "is_open": False,
                    "buy_date": lot["date"],
                    "sell_date": close_date,
                    "quantity": close_qty,
                    "buy_price": lot["cost_per_share"],
                    "sell_price": close_price,
                    "cost_basis": cost_local,
                    "proceeds_or_value": proceeds_local,
                    "gain_amount": gain_local,
                    "gain_pct": (gain_local / cost_local) if cost_local else 0.0,
                    "cost_basis_cad": cost_cad,
                    "proceeds_cad": proceeds_cad,
                    "gain_amount_cad": proceeds_cad - cost_cad,
                    "gain_pct_cad": ((proceeds_cad - cost_cad) / cost_cad) if cost_cad else 0.0,
                    "duration_days": days,
                    "duration_label": _format_duration(days),
                })

                lot["remaining_qty"] -= close_qty
                remaining -= close_qty
                if lot["remaining_qty"] <= 1e-9:
                    lots.pop(0)
            return closed

        def current_total_qty() -> float:
            return sum(l["remaining_qty"] for l in lots)

        def current_avg_cost() -> float:
            qty = current_total_qty()
            if qty <= 1e-9:
                return 0.0
            return sum(l["remaining_qty"] * l["cost_per_share"] for l in lots) / qty

        for txn in group_txns:
            ttype = txn["type"]
            qty = abs(txn["quantity"])
            txn_date = txn["date"] or _today()

            # Spinoff: once the stream reaches the effective date, scale down
            # the cost of all lots held at that point (the moved slice now
            # belongs to the child security).
            if scale_info and not scale_applied and txn_date >= scale_info[0]:
                for lot in lots:
                    lot["cost_per_share"] *= scale_info[1]
                scale_applied = True

            if ttype == "buy" and txn["quantity"] > 0:
                cost = txn["net_amount"] / txn["quantity"] if txn["quantity"] else (txn["price"] or 0)
                if cost <= 0 and txn["price"]:
                    cost = txn["price"]
                add_lot(txn_date, txn["quantity"], cost)

            elif ttype == "sell" and txn["quantity"] < 0:
                sell_price = txn["net_amount"] / qty if qty else (txn["price"] or 0)
                if sell_price <= 0 and txn["price"]:
                    sell_price = txn["price"]
                records.extend(close_lots(qty, txn_date, sell_price))

            elif ttype == "transfer":
                if txn["quantity"] > 0:
                    add_lot(txn_date, txn["quantity"], current_avg_cost())
                elif txn["quantity"] < 0:
                    avg = current_avg_cost()
                    records.extend(close_lots(qty, txn_date, avg))

            elif ttype == "other" and txn["quantity"] and txn["net_amount"] == 0:
                # Corporate action (stock split / spinoff): only rows with no
                # cash component change share counts. An "other" row with a
                # nonzero net_amount is a cash distribution (e.g. Disnat
                # return-of-capital adjustments that repeat the position size
                # in the quantity column); its cash is already reflected via
                # cash balances, so the quantity must be ignored.
                # A stock split scales existing lots, while a
                # spinoff/received-shares action (no prior position) creates
                # a new lot. A spinoff receipt is NOT $0 cost: it carries the
                # slice of the parent's basis allocated to the child.
                before = current_total_qty()
                if before > 1e-9:
                    ratio = (before + txn["quantity"]) / before
                    if ratio > 0:
                        for lot in lots:
                            lot["remaining_qty"] *= ratio
                            lot["cost_per_share"] /= ratio
                elif txn["quantity"] > 0:
                    cps = 0.0
                    if child_info and txn_date >= child_info[0]:
                        cps = child_info[1]
                    add_lot(txn_date, txn["quantity"], cps)

        # Spinoff: if no later transaction crossed the effective date (e.g.
        # an untouched open position), scale the remaining lots now.
        if scale_info and not scale_applied:
            for lot in lots:
                lot["cost_per_share"] *= scale_info[1]
            scale_applied = True

        # Remaining lots = open positions.
        current_price = sec["last_price"]
        for lot in lots:
            if lot["remaining_qty"] <= 1e-9:
                continue
            qty = lot["remaining_qty"]
            cost_local = qty * lot["cost_per_share"]
            value_local = qty * current_price if current_price else 0.0
            gain_local = value_local - cost_local

            cost_cad = _to_cad(cost_local, sec["currency"], lot["date"], fx_dates, fx_rates)
            value_cad = _to_cad(value_local, sec["currency"], _today(), fx_dates, fx_rates)

            days = _days_between(lot["date"], _today())

            records.append({
                "account_id": account_id,
                "brokerage": acct["brokerage"],
                "account_type": acct["account_type"],
                "security_id": security_id,
                "symbol": sec["symbol"],
                "name": sec["name"],
                "currency": sec["currency"],
                "sector": sec["sector"],
                "country": sec["country"],
                "is_open": True,
                "buy_date": lot["date"],
                "sell_date": None,
                "quantity": qty,
                "buy_price": lot["cost_per_share"],
                "sell_price": current_price,
                "cost_basis": cost_local,
                "proceeds_or_value": value_local,
                "gain_amount": gain_local,
                "gain_pct": (gain_local / cost_local) if cost_local else 0.0,
                "cost_basis_cad": cost_cad,
                "proceeds_cad": value_cad,
                "gain_amount_cad": value_cad - cost_cad,
                "gain_pct_cad": ((value_cad - cost_cad) / cost_cad) if cost_cad else 0.0,
                "duration_days": days,
                "duration_label": _format_duration(days),
            })

    return _consolidate(records)


def top_records(conn, sort_by: str = "pct", top_n: int = 10) -> dict:
    """Return top/bottom performer records.

    sort_by: 'pct' uses CAD-converted gain %, 'amount' uses CAD-converted $ gain.
    """
    records = compute_records(conn)
    key = "gain_pct_cad" if sort_by == "pct" else "gain_amount_cad"
    # Exclude records with no real cost basis (transfers-in at $0) so phantom
    # gains don't pollute the best/worst lists.
    valid = [r for r in records if r["cost_basis_cad"] > 1e-9]

    sorted_desc = sorted(valid, key=lambda r: r[key], reverse=True)
    sorted_asc = sorted(valid, key=lambda r: r[key])

    return {
        "best": sorted_desc[:top_n],
        "worst": sorted_asc[:top_n],
        "sort_by": sort_by,
    }
