"""Detect missing/stale price data for smart incremental fetching."""

import sqlite3
from datetime import date
from typing import Optional


def detect_price_gaps(conn: sqlite3.Connection, max_age_days: int = 3) -> dict:
    """Analyze what price data is missing.

    Returns:
        {
            "missing": [security_id, ...],      # No price history at all
            "stale": [(security_id, last_date), ...],  # Outdated data
            "fx_stale": bool,                   # FX data outdated
            "latest_fx_date": str | None,
            "today": str,
        }
    """
    today = date.today().isoformat()

    # Securities with no price history at all
    missing = conn.execute("""
        SELECT s.id FROM securities s
        LEFT JOIN price_history ph ON s.id = ph.security_id
        WHERE (s.is_cash = 0 OR s.is_cash IS NULL) AND ph.id IS NULL
    """).fetchall()

    # Securities with stale data
    stale = conn.execute("""
        SELECT s.id, MAX(ph.date) as latest
        FROM securities s
        JOIN price_history ph ON s.id = ph.security_id
        WHERE s.is_cash = 0 OR s.is_cash IS NULL
        GROUP BY s.id
        HAVING julianday(?) - julianday(MAX(ph.date)) > ?
    """, (today, max_age_days)).fetchall()

    # FX freshness
    fx_row = conn.execute("SELECT MAX(date) FROM fx_history").fetchone()
    fx_latest = fx_row[0] if fx_row else None
    fx_stale = True
    if fx_latest:
        try:
            gap = (date.fromisoformat(today) - date.fromisoformat(fx_latest)).days
            fx_stale = gap > max_age_days
        except ValueError:
            fx_stale = True

    return {
        "missing": [r["id"] for r in missing],
        "stale": [(r["id"], r["latest"]) for r in stale],
        "fx_stale": fx_stale,
        "latest_fx_date": fx_latest,
        "today": today,
    }


def has_gaps(gaps: dict) -> bool:
    """Return True if any price data is missing or stale."""
    return bool(gaps["missing"]) or bool(gaps["stale"]) or gaps["fx_stale"]
