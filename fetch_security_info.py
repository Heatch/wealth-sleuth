"""
Fetch security info from yfinance and update the securities table.

Resolves each security to a Yahoo Finance ticker, fetches fundamentals
(price, market cap, sector, industry, P/E, dividends, 52-week range),
and writes them to portfolio.db.

Ticker resolution (no lookup table, rule-based):
- USD securities: plain ticker (ACHR, GLD, TBIL)
- CDRs: {symbol}.NE first (actual CDR), then {symbol}.TO
- CAD stocks/ETFs: {symbol}.TO, then .V, then .CN, then plain

Usage:
    python fetch_security_info.py                  # update missing only
    python fetch_security_info.py --dry-run        # preview, no writes
    python fetch_security_info.py --force          # refresh everything
    python fetch_security_info.py --delay 0.5      # slower rate limit
"""

import argparse
import time
from datetime import date
from pathlib import Path
from typing import Optional

from config import DB_PATH
from database import get_connection, migrate_securities_schema


def resolve_ticker(symbol: str, currency: str, is_cdr: int) -> list[str]:
    """Return candidate Yahoo Finance tickers in preference order."""
    if currency == "USD":
        return [symbol]
    if is_cdr:
        # CDRs list on NEO (.NE gives the CDR itself; .TO falls back
        # to the underlying company quote)
        return [f"{symbol}.NE", f"{symbol}.TO"]
    # CAD stocks/ETFs: TSX (.TO), Venture (.V), CSE (.CN), then plain
    return [f"{symbol}.TO", f"{symbol}.V", f"{symbol}.CN", symbol]


def pick_name(info: dict, is_cdr: int) -> Optional[str]:
    """Pick the best display name. For CDRs prefer shortName (tags the CDR)."""
    if is_cdr:
        return info.get("shortName") or info.get("longName")
    return info.get("longName") or info.get("shortName")


def fetch_info(ticker: str) -> Optional[dict]:
    """Fetch yfinance info for a ticker. Returns None on failure."""
    import yfinance as yf

    try:
        info = yf.Ticker(ticker).info
    except Exception:
        return None
    price = info.get("regularMarketPrice") or info.get("currentPrice")
    if not info.get("longName") and not info.get("shortName"):
        return None
    if price is None:
        return None
    return info


def update_securities(
    db_path: Optional[Path] = None,
    delay: float = 0.25,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """Fetch and update securities. Returns counts dict."""
    added = migrate_securities_schema(db_path)
    if added and not dry_run:
        print(f"Added columns: {', '.join(added)}")
    elif added:
        print(f"Would add columns: {', '.join(added)} (dry run)")

    conn = get_connection(db_path)
    try:
        if force:
            rows = conn.execute(
                "SELECT id, symbol, currency, is_cdr FROM securities "
                "WHERE is_cash = 0 OR is_cash IS NULL"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, symbol, currency, is_cdr FROM securities "
                "WHERE (is_cash = 0 OR is_cash IS NULL) AND last_price IS NULL"
            ).fetchall()

        updated = 0
        failed = 0

        for row in rows:
            info = None
            used_ticker = None
            for candidate in resolve_ticker(
                row["symbol"], row["currency"], row["is_cdr"]
            ):
                info = fetch_info(candidate)
                if info is not None:
                    used_ticker = candidate
                    break
                time.sleep(0.05)

            if info is None:
                print(f"  {row['symbol']:8} NOT FOUND (skipped)")
                failed += 1
                time.sleep(delay)
                continue

            name = pick_name(info, row["is_cdr"])
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            values = {
                "last_price": price,
                "last_price_date": date.today().isoformat(),
                "market_cap": info.get("marketCap"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "description": name,
                "trailing_pe": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "dividend_yield": info.get("dividendYield"),
                "dividend_rate": info.get("dividendRate"),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            }

            sector = values["sector"] or "n/a"
            if dry_run:
                print(f"  {row['symbol']:8} -> {used_ticker:12} {str(name)[:35]:35} price={price} (dry run)")
            else:
                conn.execute(
                    """
                    UPDATE securities SET
                        last_price = ?,
                        last_price_date = ?,
                        market_cap = ?,
                        sector = ?,
                        industry = ?,
                        description = ?,
                        trailing_pe = ?,
                        forward_pe = ?,
                        dividend_yield = ?,
                        dividend_rate = ?,
                        fifty_two_week_high = ?,
                        fifty_two_week_low = ?
                    WHERE id = ?
                    """,
                    (
                        values["last_price"],
                        values["last_price_date"],
                        values["market_cap"],
                        values["sector"],
                        values["industry"],
                        values["description"],
                        values["trailing_pe"],
                        values["forward_pe"],
                        values["dividend_yield"],
                        values["dividend_rate"],
                        values["fifty_two_week_high"],
                        values["fifty_two_week_low"],
                        row["id"],
                    ),
                )
                print(f"  {row['symbol']:8} -> {used_ticker:12} {str(name)[:35]:35} price={price} sector={sector}")
            updated += 1
            time.sleep(delay)

        if not dry_run:
            conn.commit()

        return {"updated": updated, "failed": failed}
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Fetch security info from yfinance into portfolio.db."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be updated without writing",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh all securities, even ones with existing data",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="Seconds to wait between lookups (default: 0.25)",
    )

    args = parser.parse_args()

    if not args.db.exists():
        print(f"Database not found: {args.db}")
        print("Run `python consolidate.py` first.")
        return

    print("Fetching security info from yfinance...")
    result = update_securities(
        db_path=args.db,
        delay=args.delay,
        force=args.force,
        dry_run=args.dry_run,
    )
    print()
    print(f"Updated: {result['updated']}, Failed: {result['failed']}")
    if args.dry_run:
        print("(dry run — nothing was written)")


if __name__ == "__main__":
    main()
