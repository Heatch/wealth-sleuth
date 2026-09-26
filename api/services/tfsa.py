"""TFSA contribution room calculator.

Rules implemented
- TFSA started in 2009; room begins accumulating the year the taxpayer turns 18.
- Annual dollar limits are fixed by CRA and indexed to inflation in $500 steps.
- Unused room carries forward.
- Withdrawals create new contribution room, but only effective January 1 of the
  following calendar year.
- Transfers between TFSAs and internal investment activity (buys, sells,
  dividends, interest) do not affect contribution room.

For years beyond the hard-coded table we use the most recent known limit. The
limit table should be updated each year when CRA announces the new limit.
"""

import bisect
from datetime import date
from typing import Optional

# CRA TFSA annual contribution limits. Indexed to inflation in $500 increments.
ANNUAL_LIMITS = {
    2009: 5000,
    2010: 5000,
    2011: 5000,
    2012: 5000,
    2013: 5500,
    2014: 5500,
    2015: 10000,
    2016: 5500,
    2017: 5500,
    2018: 5500,
    2019: 6000,
    2020: 6000,
    2021: 6000,
    2022: 6000,
    2023: 6500,
    2024: 7000,
    2025: 7000,
    2026: 7000,
}


def annual_limit(year: int) -> int:
    """Return the CRA TFSA dollar limit for a given year.

    For future years not yet in the table, fall back to the most recent known
    limit. This keeps the display working across year boundaries until the
    table is updated.
    """
    if year in ANNUAL_LIMITS:
        return ANNUAL_LIMITS[year]
    return ANNUAL_LIMITS[max(ANNUAL_LIMITS.keys())]


def first_contribution_year(birth_year: int) -> int:
    """First year TFSA room can accumulate: later of 2009 and the year the
    taxpayer turns 18.
    """
    return max(2009, birth_year + 18)


def cumulative_room_to_year(birth_year: int, through_year: int) -> int:
    """Total accumulated annual contribution room from first eligible year
    through the given year, inclusive.
    """
    first = first_contribution_year(birth_year)
    if through_year < first:
        return 0
    return sum(annual_limit(y) for y in range(first, through_year + 1))


def _load_fx_index(conn) -> tuple[list[str], list[float]]:
    """Load USD->CAD rates into sorted arrays for bisect lookup."""
    rows = conn.execute("SELECT date, rate FROM fx_history ORDER BY date").fetchall()
    dates = [r["date"] for r in rows]
    rates = [float(r["rate"]) for r in rows]
    return dates, rates


def _to_cad(amount: float, currency: str, date_str: str, fx_dates: list[str], fx_rates: list[float]) -> float:
    """Convert an amount to CAD using the FX rate on or before the given date.

    For undated transactions, use the most recent available rate.
    """
    currency = (currency or "CAD").upper()
    if currency == "CAD" or not fx_dates:
        return amount
    if not date_str:
        rate = fx_rates[-1]
        return amount * rate
    i = bisect.bisect_right(fx_dates, date_str) - 1
    if i < 0:
        i = 0
    rate = fx_rates[i]
    return amount * rate


def load_tfsa_transactions(conn, account_ids: Optional[list[int]] = None):
    """Return all deposit/withdrawal transactions for TFSA accounts.

    USD deposits/withdrawals are converted to CAD because TFSA contribution
    room is denominated in Canadian dollars.

    Args:
        conn: SQLite connection.
        account_ids: Optional filter. If None, all TFSA accounts are included.

    Returns:
        List of dicts with keys year, type, amount (amount is positive for
        both deposits and withdrawals, and already in CAD).
    """
    params: list = []
    query = (
        "SELECT t.date, t.type, t.net_amount, t.currency "
        "FROM transactions t "
        "JOIN accounts a ON t.account_id = a.id "
        "WHERE a.account_type = 'tfsa' "
        "AND t.type IN ('deposit', 'withdrawal')"
    )
    if account_ids:
        placeholders = ",".join("?" * len(account_ids))
        query += f" AND a.id IN ({placeholders})"
        params.extend(account_ids)

    rows = conn.execute(query, params).fetchall()
    fx_dates, fx_rates = _load_fx_index(conn)
    result = []
    current_year = date.today().year
    for r in rows:
        year_str = r["date"]
        if year_str and len(year_str) >= 4:
            try:
                year = int(year_str[:4])
            except Exception:
                year = current_year
        else:
            # Undated transactions (e.g. opening contributions) count against
            # the current year's room since we cannot determine the year.
            year = current_year
        amount = abs(float(r["net_amount"] or 0.0))
        amount_cad = _to_cad(amount, r["currency"], year_str, fx_dates, fx_rates)
        result.append({"year": year, "type": r["type"], "amount": amount_cad})
    return result


def tfsa_summary(
    conn,
    birth_year: int = 2005,
    account_ids: Optional[list[int]] = None,
    current_year: Optional[int] = None,
) -> dict:
    """Compute TFSA contribution/room summary.

    Returns:
        dict with:
        - birth_year
        - year_turned_18
        - first_contribution_year
        - current_year
        - lifetime_contributions: total deposits ever made
        - lifetime_withdrawals: total withdrawals ever made
        - cumulative_room: sum of annual limits through current year
        - withdrawal_room: room created by prior-year withdrawals (already
          re-added at the start of the current year)
        - total_room: cumulative_room + withdrawal_room
        - remaining_room: total_room - lifetime_contributions
        - pct_used: lifetime_contributions / total_room (clamped 0-1)
    """
    current_year = current_year or date.today().year
    first_year = first_contribution_year(birth_year)
    year_turned_18 = birth_year + 18

    txns = load_tfsa_transactions(conn, account_ids)

    contributions_by_year: dict[int, float] = {}
    withdrawals_by_year: dict[int, float] = {}
    for t in txns:
        if t["type"] == "deposit":
            contributions_by_year[t["year"]] = contributions_by_year.get(t["year"], 0.0) + t["amount"]
        elif t["type"] == "withdrawal":
            withdrawals_by_year[t["year"]] = withdrawals_by_year.get(t["year"], 0.0) + t["amount"]

    lifetime_contributions = sum(contributions_by_year.values())
    lifetime_withdrawals = sum(withdrawals_by_year.values())

    cumulative_room = cumulative_room_to_year(birth_year, current_year)

    # Withdrawals from prior years (i.e., years before the current year) have
    # already been re-added to room on January 1 of the current year.
    withdrawal_room = sum(
        withdrawals_by_year.get(y, 0.0)
        for y in range(first_year, current_year)
    )

    total_room = cumulative_room + withdrawal_room
    remaining_room = total_room - lifetime_contributions

    pct_used = 0.0
    if total_room > 0:
        pct_used = min(1.0, max(0.0, lifetime_contributions / total_room))

    return {
        "birth_year": birth_year,
        "year_turned_18": year_turned_18,
        "first_contribution_year": first_year,
        "current_year": current_year,
        "lifetime_contributions": lifetime_contributions,
        "lifetime_withdrawals": lifetime_withdrawals,
        "cumulative_room": cumulative_room,
        "withdrawal_room": withdrawal_room,
        "total_room": total_room,
        "remaining_room": remaining_room,
        "pct_used": pct_used,
    }
