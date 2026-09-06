"""Return calculations: time-weighted (TWR), money-weighted (MWR/IRR), naive."""

import sqlite3
from datetime import date
from typing import Optional


def period_start(period: str, series: list, today: str) -> str:
    """Resolve the start date for a period toggle given a date series."""
    dates = [d for d, _ in series]
    if not dates:
        return today
    if period == "all":
        return dates[0]
    if period == "ytd":
        jan1 = today[:4] + "-01-01"
        for d in dates:
            if d >= jan1:
                return d
        return dates[-1]
    months = {"1m": 1, "6m": 6, "1y": 12, "3y": 36}.get(period, 12)
    y, m, d = int(today[:4]), int(today[5:7]), int(today[8:10])
    m -= months
    while m <= 0:
        m += 12
        y -= 1
    cutoff = f"{y:04d}-{m:02d}-{d:02d}"
    for dt in dates:
        if dt >= cutoff:
            return dt
    return dates[-1]


def slice_series(series: list, start: str) -> list:
    """Return [(date, value)] for dates >= start."""
    return [(d, v) for d, v in series if d >= start]


def naive_return(start_value: float, end_value: float, net_flows: float) -> Optional[float]:
    """Modified Dietz simple return: (end - start - flows) / |start + 0.5*flows|."""
    denom = abs(start_value + 0.5 * net_flows)
    if denom == 0:
        return None
    return (end_value - start_value - net_flows) / denom


def twr_return(sub: list, flows: dict) -> Optional[float]:
    """Time-weighted return via daily geometric linking (Modified Dietz, W=0.5)."""
    if len(sub) < 2:
        return None
    linked = 1.0
    any_valid = False
    for i in range(1, len(sub)):
        prev_d, prev_v = sub[i - 1]
        cur_d, cur_v = sub[i]
        cf = flows.get(cur_d, 0.0) or 0.0
        denom = prev_v + 0.5 * cf
        if denom == 0:
            continue
        r = (cur_v - prev_v - cf) / denom
        linked *= 1.0 + r
        any_valid = True
    if not any_valid:
        return None
    return linked - 1.0


def mwr_return(sub: list, flows: dict) -> Optional[float]:
    """Money-weighted return (period return, de-annualized IRR) via bisection.

    Solves for the annualized IRR, then converts to the cumulative period
    return so it is directly comparable with TWR: (1+r)^(days/365) - 1.
    """
    if len(sub) < 2:
        return None
    start_d = sub[0][0]
    end_d, end_v = sub[-1]
    days_total = (parse_date(end_d) - parse_date(start_d)).days
    if days_total <= 0:
        return naive_return(sub[0][1], end_v, sum(flows.get(d, 0.0) or 0.0 for d, _ in sub))
    start_v = sub[0][1]
    pts = [(-start_v, 0.0)]
    for d, _ in sub[1:]:
        cf = flows.get(d, 0.0) or 0.0
        if cf:
            t = (parse_date(d) - parse_date(start_d)).days / 365.0
            pts.append((-cf, t))
    t_end = days_total / 365.0
    pts.append((end_v, t_end))

    def npv(r):
        total = 0.0
        for amt, t in pts:
            total += amt / ((1.0 + r) ** t) if t > 0 else amt
        return total

    lo, hi = -0.9999, 10.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return naive_return(start_v, end_v, sum(flows.get(d, 0.0) or 0.0 for d, _ in sub))
    annualized = None
    for _ in range(200):
        mid = (lo + hi) / 2.0
        f_mid = npv(mid)
        if abs(f_mid) < 1e-9:
            annualized = mid
            break
        if f_lo * f_mid <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    if annualized is None:
        annualized = (lo + hi) / 2.0
    return (1.0 + annualized) ** (days_total / 365.0) - 1.0


def parse_date(s: str):
    """Parse YYYY-MM-DD to date."""
    from datetime import date as _date
    return _date(int(s[:4]), int(s[5:7]), int(s[8:10]))


def period_returns(series: list, flows: dict, period: str) -> dict:
    """Compute twr/mwr/naive for one period. Returns dict of floats/None."""
    if not series:
        return {"twr": None, "mwr": None, "naive": None}
    today = series[-1][0]
    start = period_start(period, series, today)
    sub = slice_series(series, start)
    if len(sub) < 2:
        return {"twr": None, "mwr": None, "naive": None}
    start_v = sub[0][1]
    end_v = sub[-1][1]
    net_flows = sum(flows.get(d, 0.0) or 0.0 for d, _ in sub[1:])
    return {
        "twr": twr_return(sub, flows),
        "mwr": mwr_return(sub, flows),
        "naive": naive_return(start_v, end_v, net_flows),
    }


def all_period_returns(series: list, flows: dict) -> dict:
    """Compute returns for every chart period toggle."""
    out = {}
    for p in ("1m", "6m", "ytd", "1y", "3y", "all"):
        out[p] = period_returns(series, flows, p)
    return out

