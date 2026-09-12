"""Live price refresh - updates securities.last_price every 15 minutes.

Unlike fetch_price_history.py (historical daily closes for charting),
this fetches only the current price via yfinance .info for the holdings
table. Runs in a background thread while the API is active.
"""

import time
from pathlib import Path
from typing import Optional

from config import DB_PATH
from database import get_connection


def refresh_live_prices(db_path: Optional[Path] = None) -> dict:
    """Fetch current prices for all non-cash securities.

    Returns {"updated": N, "failed": M}.
    """
    from fetch_security_info import fetch_info, resolve_ticker

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT id, symbol, currency, is_cdr FROM securities "
            "WHERE is_cash = 0 OR is_cash IS NULL"
        ).fetchall()

        updated = 0
        failed = 0

        for row in rows:
            info = None
            for candidate in resolve_ticker(
                row["symbol"], row["currency"], row["is_cdr"]
            ):
                info = fetch_info(candidate)
                if info is not None:
                    break
                time.sleep(0.05)

            if info is None:
                failed += 1
                time.sleep(0.25)
                continue

            price = info.get("regularMarketPrice") or info.get("currentPrice")
            if price is None:
                failed += 1
                time.sleep(0.25)
                continue

            conn.execute(
                "UPDATE securities SET last_price = ?, last_price_date = date('now') WHERE id = ?",
                (float(price), row["id"]),
            )
            updated += 1
            time.sleep(0.25)

        conn.commit()
        return {"updated": updated, "failed": failed}
    finally:
        conn.close()


def live_price_loop(interval_seconds: float = 900.0):
    """Background loop: refresh live prices every 15 minutes (default)."""
    from api.cache import cache

    while True:
        time.sleep(interval_seconds)
        try:
            result = refresh_live_prices()
            cache.invalidate_on_price_update()
            print(f"Live prices refreshed: {result['updated']} updated, {result['failed']} failed.")
        except Exception as e:
            print(f"Live price refresh failed: {e}")
