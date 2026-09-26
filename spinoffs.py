"""Spinoff cost-basis reallocation (e.g. TC Energy -> South Bow, Oct 2024).

A spinoff is NOT free shares: part of the parent's cost basis moves to the
child, so the parent's basis drops and the child's starts above zero. Gains
are then plain price appreciation on each leg.

Known events and their official cost allocations live in SPINOFFS below (add
future spinoffs here):
- TRP -> SOBO, Oct 1 2024: 0.2 SOBO per TRP share; 91% of pre-spinoff TRP
  cost stays with TRP, 9% moves to SOBO (per TC Energy's Canadian ACB notice
  and IRS Form 8937). No gain/loss on receipt itself.
"""

from datetime import date

# (parent_symbol, child_symbol) -> event details.
# child_pct: fraction of the parent's pre-spinoff cost basis that moves to
#   the child. ratio: child shares issued per parent share (sanity check).
# window_days: how far a recorded receipt may be from the event date.
SPINOFFS = {
    ("TRP", "SOBO"): {
        "event_date": "2024-10-01",
        "ratio": 0.2,
        "child_pct": 0.09,
        "window_days": 60,
    },
}


def _to_date(s: str):
    try:
        return date.fromisoformat((s or "")[:10])
    except Exception:
        return None


def _replay_cost_to_date(txns: list[dict], before_date: str) -> tuple[float, float]:
    """Replay buy/sell/transfer/total-cost up to (not incl.) before_date.

    Mirrors the FIFO cost rules in records.py / refresh_holdings.py:
    buys add cost, sells remove it proportionally, transfers move at average
    cost. Splits and $0-cost receipts preserve total cost, so they are
    irrelevant here; cash-only "other" rows never touch cost basis.
    Returns (quantity, total_cost).
    """
    qty = 0.0
    cost = 0.0
    for t in txns:
        d = t["date"] or ""
        if d >= before_date:
            continue
        ttype = t["type"]
        q = float(t["quantity"] or 0)
        net = float(t["net_amount"] or 0)
        price = float(t["price"] or 0) if t["price"] else 0.0
        if ttype == "buy" and q > 0:
            cost += abs(net) if net else price * q
            qty += q
        elif ttype == "sell" and q < 0:
            out = abs(q)
            if qty > 1e-9:
                cost -= (cost / qty) * out
            qty -= out
        elif ttype == "transfer":
            if q > 0:
                avg = (cost / qty) if qty > 1e-9 else 0.0
                cost += avg * q
                qty += q
            elif q < 0:
                out = abs(q)
                if qty > 1e-9:
                    cost -= (cost / qty) * out
                qty -= out
    return qty, cost


def spinoff_adjustments(conn):
    """Compute cost-basis reallocations for known spinoffs.

    Returns (parent_scales, child_costs):
    - parent_scales[(account_id, parent_sec_id)] = (adj_date, scale)
      Multiply the cost of parent lots held on adj_date by scale.
    - child_costs[(account_id, child_sec_id)] = (receipt_date, cost_per_share)
      Cost basis for the spun-off receipt instead of $0.
    """
    parent_scales: dict = {}
    child_costs: dict = {}

    secs = {r["id"]: r["symbol"] for r in conn.execute("SELECT id, symbol FROM securities").fetchall()}
    sec_ids = {sym: sid for sid, sym in secs.items()}

    for (parent_sym, child_sym), spec in SPINOFFS.items():
        if parent_sym not in sec_ids or child_sym not in sec_ids:
            continue
        pid, cid = sec_ids[parent_sym], sec_ids[child_sym]
        event = _to_date(spec["event_date"])
        window = spec.get("window_days", 60)
        ratio = spec.get("ratio")
        child_pct = spec["child_pct"]

        # Child receipts: "other" rows with shares but no cash, near the event.
        receipts = conn.execute(
            "SELECT account_id, date, quantity FROM transactions "
            "WHERE security_id = ? AND type = 'other' "
            "AND quantity > 0 AND (net_amount IS NULL OR net_amount = 0)",
            (cid,),
        ).fetchall()

        by_account: dict[int, list] = {}
        for r in receipts:
            d = _to_date(r["date"])
            if d is None or event is None or abs((d - event).days) > window:
                continue
            by_account.setdefault(r["account_id"], []).append((r["date"], float(r["quantity"])))

        for account_id, recs in by_account.items():
            recs.sort()
            receipt_date = recs[0][0]
            child_qty = sum(q for _, q in recs)

            # Parent cost just before the receipt.
            parent_txns = [
                {"date": t["date"] or "", "type": t["type"],
                 "quantity": t["quantity"], "net_amount": t["net_amount"], "price": t["price"]}
                for t in conn.execute(
                    "SELECT date, type, quantity, net_amount, price FROM transactions "
                    "WHERE account_id = ? AND security_id = ? "
                    "AND type IN ('buy', 'sell', 'transfer') ORDER BY date, id",
                    (account_id, pid),
                ).fetchall()
            ]
            parent_qty, parent_cost = _replay_cost_to_date(parent_txns, receipt_date)

            if parent_cost <= 1e-9 or child_qty <= 1e-9:
                continue

            if ratio and parent_qty > 1e-9:
                expected = parent_qty * ratio
                if abs(expected - child_qty) / expected > 0.05:
                    print(
                        f"Warning: spinoff {parent_sym}->{child_sym} receipt "
                        f"{child_qty} differs from expected {expected:.4f} "
                        f"(account {account_id}); skipping"
                    )
                    continue

            child_cps = parent_cost * child_pct / child_qty
            parent_scales[(account_id, pid)] = (receipt_date, 1.0 - child_pct)
            child_costs[(account_id, cid)] = (receipt_date, child_cps)

    return parent_scales, child_costs
