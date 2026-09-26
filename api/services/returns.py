"""Return calculations: Time-Weighted Return (TWR) and XIRR (money-weighted).

Both metrics are built from the daily valuation series produced by
`api.services.valuation`.  TWR links daily sub-period returns so it reflects
pure investment performance, while XIRR solves for the internal rate of return
using the actual dates of external cash flows, so it reflects the investor's
personal return.
"""

from datetime import date
from typing import Optional

PERIODS = ("1m", "6m", "ytd", "1y", "3y", "all")


def parse_date(s: str) -> date:
    """Parse YYYY-MM-DD to a date object."""
    return date(int(s[:4]), int(s[5:7]), int(s[8:10]))


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


def _years_between(dates: list[date], base: date) -> list[float]:
    return [(d - base).days / 365.0 for d in dates]


def _npv(rate: float, amounts: list[float], years: list[float]) -> float:
    """Net present value at a given annualized rate."""
    if rate <= -1.0:
        rate = -0.999999999999
    total = 0.0
    for amt, yr in zip(amounts, years):
        total += amt / ((1.0 + rate) ** yr)
    return total


def _solve_xirr(dates: list[date], amounts: list[float]) -> Optional[float]:
    """Solve for the annualized IRR of a cash-flow stream.

    Uses bisection with an expanding upper bound, which is robust enough
    for both small personal portfolios and very short/high-return periods.
    Returns None when no meaningful root exists.
    """
    if len(dates) < 2 or len(amounts) != len(dates):
        return None

    base = dates[0]
    years = _years_between(dates, base)
    days = years[-1] * 365.0
    if days <= 0:
        return None

    # Trivial case: only an initial and final value.
    if len(amounts) == 2:
        if amounts[0] == 0.0:
            return None
        ratio = -amounts[1] / amounts[0]
        if ratio <= 0.0:
            return None
        return ratio ** (1.0 / years[1]) - 1.0

    npv0 = sum(amounts)
    if abs(npv0) < 1e-9:
        return 0.0

    lo, hi = -0.9999, 100.0
    f_lo = _npv(lo, amounts, years)
    f_hi = _npv(hi, amounts, years)

    # Expand the bracket until we find a sign change.
    max_hi = 1e9
    while f_lo * f_hi > 0.0 and hi < max_hi:
        hi *= 2.0
        if hi > max_hi:
            hi = max_hi
        f_hi = _npv(hi, amounts, years)
        if f_hi == f_lo:
            break

    if f_lo * f_hi <= 0.0:
        for _ in range(120):
            mid = (lo + hi) / 2.0
            f_mid = _npv(mid, amounts, years)
            if abs(f_mid) < 1e-9:
                return mid
            if f_lo * f_mid <= 0.0:
                hi, f_hi = mid, f_mid
            else:
                lo, f_lo = mid, f_mid
        return (lo + hi) / 2.0

    # No bracket found; XIRR is undefined for this cash-flow pattern.
    return None


def xirr_return(sub: list, flows: dict, segment_mode: bool = False) -> Optional[float]:
    """Annualized XIRR for a valuation sub-series and external cash flows.

    Cash-flow convention (investor perspective):
      * start value  -> negative (money invested)
      * deposits     -> negative (additional money invested)
      * withdrawals  -> positive (money returned)
      * end value    -> positive (money returned)

    The opening value is the end-of-day value, so a cash flow on the first
    date is already inside it and is not applied again. Later flows, including
    a trade on the final day, are included.
    """
    if len(sub) < 2:
        return None

    start_date = parse_date(sub[0][0])
    end_date = parse_date(sub[-1][0])
    if (end_date - start_date).days <= 0:
        return None

    dates = [start_date]
    amounts = [-sub[0][1]]

    for d, _ in sub[1:]:
        # Start-day flows are already inside the opening value. Later flows,
        # including a buy on the final day, are real cash movements and must
        # be included or that buy is mistaken for investment gain.
        cf = flows.get(d, 0.0) or 0.0
        if cf:
            dates.append(parse_date(d))
            amounts.append(-cf)

    dates.append(end_date)
    amounts.append(sub[-1][1])

    return _solve_xirr(dates, amounts)


def twr_return(sub: list, flows: dict, handle_zero_start: bool = False) -> Optional[float]:
    """Cumulative Time-Weighted Return via daily geometric linking.

    Each daily sub-period return uses the Modified-Dietz midpoint assumption
    for cash flows, which is the best available approximation when only
    end-of-day valuations are known.

    When *handle_zero_start* is True, days where the previous value is zero
    and a positive flow is invested are handled as a return on the newly
    invested capital. This is needed for segment filters, where the slice's
    market value can drop to zero between trades.
    """
    if len(sub) < 2:
        return None

    linked = 1.0
    any_valid = False
    for i in range(1, len(sub)):
        prev_d, prev_v = sub[i - 1]
        cur_d, cur_v = sub[i]
        cf = flows.get(cur_d, 0.0) or 0.0
        if handle_zero_start and abs(prev_v) < 1e-9:
            if cf > 1e-9:
                # Money invested into an empty slice: measure the return on
                # that new capital from the day it was invested.
                denom = cf
                r = (cur_v - cf) / denom
            elif cf < -1e-9:
                # Money withdrawn from an empty slice (e.g., dividend after a
                # sale) has an undefined return; skip the day.
                continue
            else:
                continue
        else:
            denom = prev_v + 0.5 * cf
            if denom == 0.0:
                continue
            r = (cur_v - prev_v - cf) / denom
        linked *= 1.0 + r
        any_valid = True

    if not any_valid:
        return None
    return linked - 1.0


def _trim_leading_zeros(sub: list) -> list:
    """Drop leading zero-value days so returns start from the first real value."""
    for i, (_, v) in enumerate(sub):
        if abs(v) > 1e-9:
            return sub[i:]
    return []


def linked_twr(dates: list, daily_returns: dict) -> Optional[float]:
    """Compound precomputed holding-period returns from the second date onward.

    The first date is the baseline (0%). Each later day's return is the price
    change of shares already held, so money added that day is not performance.
    """
    if len(dates) < 2:
        return None
    linked = 1.0
    for d in dates[1:]:
        r = daily_returns.get(d, 0.0) or 0.0
        if r <= -1.0:
            r = -0.999999
        linked *= 1.0 + r
    return linked - 1.0


def period_returns(
    sub: list,
    flows: dict,
    handle_zero_start: bool = False,
    segment_mode: bool = False,
    daily_returns: Optional[dict] = None,
) -> dict:
    """Compute XIRR and TWR for a pre-sliced sub-series."""
    sub = _trim_leading_zeros(sub)
    if len(sub) < 2:
        return {"xirr": None, "twr": None}
    if daily_returns is not None:
        # Compound the return of capital already invested. New deposits and
        # buys earn nothing on the day they arrive, so they are not performance.
        twr = linked_twr([d for d, _ in sub], daily_returns)
    else:
        twr = twr_return(sub, flows, handle_zero_start=handle_zero_start)
    return {
        "xirr": xirr_return(sub, flows, segment_mode=segment_mode),
        "twr": twr,
    }


def all_period_returns(
    series: list,
    flows: dict,
    handle_zero_start: bool = False,
    segment_mode: bool = False,
    daily_returns: Optional[dict] = None,
) -> dict:
    """Compute XIRR/TWR for every chart period toggle."""
    out = {}
    if not series:
        for p in PERIODS:
            out[p] = {"xirr": None, "twr": None}
        return out
    today = series[-1][0]
    for p in PERIODS:
        start = period_start(p, series, today)
        sub = slice_series(series, start)
        out[p] = period_returns(
            sub, flows,
            handle_zero_start=handle_zero_start,
            segment_mode=segment_mode,
            daily_returns=daily_returns,
        )
    return out


def point_returns(
    sub: list,
    flows: dict,
    handle_zero_start: bool = False,
    segment_mode: bool = False,
    daily_returns: Optional[dict] = None,
) -> list[dict]:
    """Cumulative XIRR and TWR from the first real point of *sub* to each point.

    The result list is the same length as *sub* so it can be zipped with the
    original series. Leading zero-value days get null returns; the first
    non-zero point has a TWR of 0%.
    """
    if not sub:
        return []

    first_idx = None
    for i, (_, v) in enumerate(sub):
        if abs(v) > 1e-9:
            first_idx = i
            break
    if first_idx is None:
        return [{"xirr": None, "twr": None} for _ in sub]

    trimmed = sub[first_idx:]
    flow_list = [(d, flows.get(d, 0.0) or 0.0) for d, _ in trimmed]
    results: list[dict] = []
    linked = 1.0
    use_linked = daily_returns is not None
    for i in range(len(trimmed)):
        if i == 0:
            results.append({"xirr": None, "twr": 0.0})
            continue
        point_sub = trimmed[: i + 1]
        point_flows = {d: v for d, v in flow_list[: i + 1] if v}
        if use_linked:
            r = daily_returns.get(trimmed[i][0], 0.0) or 0.0
            if r <= -1.0:
                r = -0.999999
            linked *= 1.0 + r
            twr = linked - 1.0
        else:
            twr = twr_return(point_sub, point_flows, handle_zero_start=handle_zero_start)
        results.append({
            "xirr": xirr_return(point_sub, point_flows, segment_mode=segment_mode),
            "twr": twr,
        })

    return [{"xirr": None, "twr": None} for _ in range(first_idx)] + results


def portfolio_returns(
    series: list,
    flows: dict,
    deposits: dict,
    undated_dep: float,
    segment_mode: bool = False,
    daily_returns: Optional[dict] = None,
) -> dict:
    """Full return package used by the API: every period + per-period chart data."""
    out = {
        "periods": all_period_returns(
            series, flows,
            handle_zero_start=segment_mode,
            segment_mode=segment_mode,
            daily_returns=daily_returns,
        ),
        "history": {},
    }
    if not series:
        for p in PERIODS:
            out["history"][p] = []
        return out

    today = series[-1][0]
    # Cumulative net deposits (including security transfers) for the chart.
    cum = undated_dep
    cum_map: dict[str, float] = {}
    for d, _ in series:
        cum += deposits.get(d, 0.0) or 0.0
        cum_map[d] = cum

    for p in PERIODS:
        start = period_start(p, series, today)
        sub = slice_series(series, start)
        if len(sub) < 2:
            out["history"][p] = []
            continue
        pret = point_returns(
            sub, flows,
            handle_zero_start=segment_mode,
            segment_mode=segment_mode,
            daily_returns=daily_returns,
        )
        out["history"][p] = [
            {
                "date": d,
                "value": v,
                "net_deposits": cum_map[d],
                "return_xirr": r["xirr"],
                "return_twr": r["twr"],
            }
            for (d, v), r in zip(sub, pret)
        ]
    return out


def portfolio_returns_cached(
    currency: str = "CAD", account_ids: Optional[list] = None, security_ids: Optional[list] = None
) -> dict:
    """Cache the full return package per (currency, account filter, security filter).

    The underlying daily valuations are also cached, so the full dashboard
    (summary + history) shares one computation.
    """
    from api.cache import cache
    from api.services.valuation import daily_portfolio_values_cached

    acct_key = tuple(sorted(account_ids)) if account_ids else "all"
    sec_key = tuple(sorted(security_ids)) if security_ids else "all"
    # v4 bump: slice TWR is a holding-period compound, not (end - start) / start.
    key = f"returns_v7_{currency}_{acct_key}_{sec_key}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    series, flows, cash_total, _undated_base, undated_dep, deposits, daily_returns = daily_portfolio_values_cached(
        currency, account_ids, security_ids
    )
    result = portfolio_returns(
        series, flows, deposits, undated_dep,
        segment_mode=security_ids is not None,
        daily_returns=daily_returns,
    )
    result["cash_total"] = cash_total
    cache.set(key, result)
    return result
