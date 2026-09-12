"""Fetch historical daily prices from yfinance into price_history + fx_history."""

import argparse
import math
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from config import DB_PATH
from database import get_connection, init_db
from fetch_security_info import resolve_ticker


def resolve_ticker_for_history(symbol: str, currency: str, is_cdr: int) -> list[str]:
    """Return candidate tickers for price history, preferring reliable feeds.

    CDRs: .TO first (.NE history goes stale/NaN after July 2026).
    Others: same order as resolve_ticker().
    """
    cands = resolve_ticker(symbol, currency, is_cdr)
    if is_cdr and currency != "USD":
        # Prefer .TO for history (NEO feed has NaN closes after Jul 2026)
        to_first = sorted(cands, key=lambda t: (0 if t.endswith(".TO") else 1, t))
        # Deduplicate while preserving order
        seen = set()
        ordered = []
        for t in to_first:
            if t not in seen:
                seen.add(t)
                ordered.append(t)
        return ordered
    return cands


def is_fresh_enough(df, max_age_days: int = 7) -> bool:
    """Check if the most recent valid close is within max_age_days of today."""
    if df is None or df.empty or "Close" not in df.columns:
        return False
    valid = df[df["Close"].notna()]
    if valid.empty:
        return False
    latest = valid.index[-1].date()
    today = date.today()
    return (today - latest).days <= max_age_days


def fetch_history(ticker: str):
    """Fetch full daily history. Returns DataFrame or None."""
    import yfinance as yf
    try:
        df = yf.Ticker(ticker).history(period="max", auto_adjust=False)
    except Exception:
        return None
    if df is None or df.empty or "Close" not in df.columns:
        return None
    # Filter out NaN closes (.NE tickers return NaN after Jul 2026)
    valid_count = int(df["Close"].notna().sum())
    if valid_count == 0:
        return None
    return df


def update_price_history(
    db_path: Optional[Path] = None,
    delay: float = 0.25,
    force: bool = False,
    dry_run: bool = False,
    only_symbol: Optional[str] = None,
) -> dict:
    """Fetch and store price history. Returns counts dict."""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        if only_symbol:
            q = "SELECT id, symbol, currency, is_cdr FROM securities "
            q += "WHERE symbol = ? AND (is_cash = 0 OR is_cash IS NULL)"
            rows = conn.execute(q, (only_symbol,)).fetchall()
        else:
            q = "SELECT id, symbol, currency, is_cdr FROM securities "
            q += "WHERE is_cash = 0 OR is_cash IS NULL"
            rows = conn.execute(q).fetchall()

        updated_secs = 0
        failed_secs = 0
        inserted_rows = 0

        for row in rows:
            df = None
            used_ticker = None
            cands = resolve_ticker_for_history(row["symbol"], row["currency"], row["is_cdr"])
            for candidate in cands:
                df = fetch_history(candidate)
                if df is not None and is_fresh_enough(df):
                    used_ticker = candidate
                    break
                df = None
                time.sleep(0.05)

            if df is None:
                print("  " + row["symbol"] + " NOT FOUND (skipped)")
                failed_secs += 1
                time.sleep(delay)
                continue

            if force:
                existing = set()
            else:
                existing = set(
                    r["date"] for r in conn.execute(
                        "SELECT date FROM price_history WHERE security_id = ?",
                        (row["id"],),
                    ).fetchall()
                )

            new_rows = 0
            for ts, data in df.iterrows():
                date_str = ts.strftime("%Y-%m-%d")
                if date_str in existing:
                    continue
                try:
                    close_val = float(data.get("Close"))
                except (TypeError, ValueError):
                    continue
                if math.isnan(close_val) or math.isinf(close_val):
                    continue
                if dry_run:
                    new_rows += 1
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO price_history "
                    "(security_id, date, close_price, currency) "
                    "VALUES (?, ?, ?, ?)",
                    (row["id"], date_str, close_val, row["currency"]),
                )
                new_rows += 1

            if not dry_run:
                conn.commit()
            inserted_rows += new_rows
            tag = "(dry run)" if dry_run else ""
            print("  " + row["symbol"] + " -> " + str(used_ticker) + " +" + str(new_rows) + " rows " + tag)
            updated_secs += 1
            time.sleep(delay)

        fx_rows = fetch_fx_history(conn, delay=delay, force=force, dry_run=dry_run)
        if not dry_run:
            conn.commit()

        return {
            "securities_updated": updated_secs,
            "securities_failed": failed_secs,
            "price_rows": inserted_rows,
            "fx_rows": fx_rows,
        }
    finally:
        conn.close()


def fetch_fx_history(conn, delay=0.25, force=False, dry_run=False):
    """Fetch USDCAD=X history into fx_history. Returns rows inserted."""
    import yfinance as yf

    try:
        df = yf.Ticker("USDCAD=X").history(period="max", auto_adjust=False)
    except Exception as e:
        print("  USDCAD=X FAILED: " + str(e))
        return 0
    if df is None or df.empty:
        print("  USDCAD=X returned no data")
        return 0

    if force:
        existing = set()
    else:
        existing = set(
            r["date"] for r in conn.execute("SELECT date FROM fx_history").fetchall()
        )

    count = 0
    for ts, data in df.iterrows():
        date_str = ts.strftime("%Y-%m-%d")
        if date_str in existing:
            continue
        try:
            rate = float(data.get("Close"))
        except (TypeError, ValueError):
            continue
        if math.isnan(rate) or math.isinf(rate):
            continue
        if dry_run:
            count += 1
            continue
        conn.execute(
            "INSERT OR IGNORE INTO fx_history (date, rate) VALUES (?, ?)",
            (date_str, rate),
        )
        count += 1

    tag = "(dry run)" if dry_run else ""
    print("  USDCAD=X +" + str(count) + " rows " + tag)
    time.sleep(delay)
    return count


def fetch_incremental(db_path=None, delay: float = 0.25) -> dict:
    """Fetch only missing/stale price data based on gap detection.

    Uses detect_price_gaps() to find securities with no data or stale
    data, then fetches just what's needed. Called by the API startup
    handler in a background thread.
    """
    from api.services.price_gaps import detect_price_gaps
    from database import get_connection

    conn = get_connection(db_path)
    try:
        gaps = detect_price_gaps(conn)
    finally:
        conn.close()

    if not gaps["missing"] and not gaps["stale"] and not gaps["fx_stale"]:
        print("Price data is current. Nothing to fetch.")
        return {"securities_updated": 0, "securities_failed": 0,
                "price_rows": 0, "fx_rows": 0}

    print(f"Fetching gaps: {len(gaps['missing'])} new, "
          f"{len(gaps['stale'])} stale securities...")
    # update_price_history already skips existing dates, so a normal
    # run only fetches what's missing. Force=False keeps it incremental.
    return update_price_history(
        db_path=db_path, delay=delay, force=False, dry_run=False,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Fetch historical prices from yfinance into portfolio.db."
    )
    parser.add_argument("--db", type=Path, default=DB_PATH,
        help="Path to SQLite database")
    parser.add_argument("--dry-run", action="store_true",
        help="Preview what would be fetched without writing")
    parser.add_argument("--force", action="store_true",
        help="Re-fetch all history, even dates already stored")
    parser.add_argument("--security", type=str, default=None,
        help="Fetch only this canonical symbol (for testing)")
    parser.add_argument("--delay", type=float, default=0.25,
        help="Seconds to wait between lookups (default: 0.25)")

    args = parser.parse_args()

    if not args.db.exists():
        print("Database not found: " + str(args.db))
        print("Run `python consolidate.py` first.")
        return

    print("Fetching price history from yfinance...")
    result = update_price_history(
        db_path=args.db,
        delay=args.delay,
        force=args.force,
        dry_run=args.dry_run,
        only_symbol=args.security,
    )
    print("")
    print("Securities updated: " + str(result["securities_updated"])
        + ", Failed: " + str(result["securities_failed"])
        + ", Price rows: " + str(result["price_rows"])
        + ", FX rows: " + str(result["fx_rows"]))
    if args.dry_run:
        print("(dry run - nothing was written)")


if __name__ == "__main__":
    main()

