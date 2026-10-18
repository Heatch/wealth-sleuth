"""Live price refresh - updates securities every 15 minutes.

Unlike fetch_price_history.py (historical daily closes for charting),
this fetches the current snapshot via yfinance .info for the holdings
table. It refreshes the price *and* the fundamentals (market cap, P/E,
dividend yield, 52-week range) so the DB-backed table stays consistent
with the company card's on-demand enrichment. Runs in a background
thread while the API is active.
"""

import time
from pathlib import Path
from typing import Optional

from config import DB_PATH
from database import get_connection


def _mark_price_update(conn) -> None:
    """Record when live prices were last refreshed (drives UI refresh)."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.execute(
        "INSERT OR REPLACE INTO app_state (key, value) "
        "VALUES ('last_price_update', datetime('now'))"
    )


def refresh_live_prices(db_path: Optional[Path] = None) -> dict:
    """Fetch current prices (and fundamentals) for all non-cash securities.

    Returns {"updated": N, "failed": M}.
    """
    from fetch_security_info import (
        CRYPTO_SECTOR,
        build_values_from_info,
        classify_crypto,
        fetch_info,
        resolve_ticker,
    )

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT id, symbol, currency, is_cdr, asset_class FROM securities "
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

            values = build_values_from_info(info, row["is_cdr"], row["asset_class"])
            if values["last_price"] is None:
                failed += 1
                time.sleep(0.25)
                continue

            # Crypto names may override a generic yfinance sector.
            crypto, strong = classify_crypto(
                f"{values['description'] or ''} {row['symbol']}"
            )
            sector_in = CRYPTO_SECTOR if (crypto and strong) else values["sector"]

            # COALESCE keeps existing values when a given fetch returns
            # null, so a partial yfinance response never wipes stored data.
            conn.execute(
                """
                UPDATE securities SET
                    last_price = ?,
                    last_price_date = date('now'),
                    market_cap = COALESCE(?, market_cap),
                    trailing_pe = COALESCE(?, trailing_pe),
                    forward_pe = COALESCE(?, forward_pe),
                    dividend_yield = COALESCE(?, dividend_yield),
                    dividend_rate = COALESCE(?, dividend_rate),
                    fifty_two_week_high = COALESCE(?, fifty_two_week_high),
                    fifty_two_week_low = COALESCE(?, fifty_two_week_low),
                    sector = COALESCE(?, sector),
                    industry = COALESCE(?, industry),
                    country = COALESCE(?, country)
                WHERE id = ?
                """,
                (
                    values["last_price"],
                    values["market_cap"],
                    values["trailing_pe"],
                    values["forward_pe"],
                    values["dividend_yield"],
                    values["dividend_rate"],
                    values["fifty_two_week_high"],
                    values["fifty_two_week_low"],
                    sector_in,
                    values["industry"],
                    values["country"],
                    row["id"],
                ),
            )
            updated += 1
            time.sleep(0.25)

        _mark_price_update(conn)
        conn.commit()
        return {"updated": updated, "failed": failed}
    finally:
        conn.close()


def live_price_loop(interval_seconds: float = 900.0):
    """Background loop: refresh live prices now, then every interval.

    Refreshes once immediately on startup so the table has current prices
    without waiting a full interval, then repeats every 15 minutes.
    """
    from api.cache import cache

    while True:
        try:
            result = refresh_live_prices()
            cache.invalidate_on_price_update()
            print(f"Live prices refreshed: {result['updated']} updated, {result['failed']} failed.")
        except Exception as e:
            print(f"Live price refresh failed: {e}")
        time.sleep(interval_seconds)
