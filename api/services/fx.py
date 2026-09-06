"""FX rate helpers for historical and current valuation."""

import sqlite3


def get_fx_rate_on(conn, date_str):
    """USD->CAD rate for a date (nearest previous available)."""
    row = conn.execute(
        "SELECT rate FROM fx_history WHERE date <= ? ORDER BY date DESC LIMIT 1",
        (date_str,),
    ).fetchone()
    if row:
        return float(row["rate"])
    row = conn.execute(
        "SELECT rate FROM fx_history ORDER BY date ASC LIMIT 1"
    ).fetchone()
    if row:
        return float(row["rate"])
    return 1.0


def get_latest_fx_rate(conn):
    """Most recent USD->CAD rate and its date."""
    row = conn.execute(
        "SELECT date, rate FROM fx_history ORDER BY date DESC LIMIT 1"
    ).fetchone()
    if row:
        return float(row["rate"]), row["date"]
    return 1.0, ""


def convert(amount, from_currency, to_currency, rate):
    """Convert an amount between CAD and USD using the given rate."""
    if from_currency == to_currency:
        return amount
    if from_currency == "USD" and to_currency == "CAD":
        return amount * rate
    if from_currency == "CAD" and to_currency == "USD":
        return amount / rate if rate else amount
    return amount

