"""
Fetch security info from yfinance and update the securities table.

Resolves each security to a Yahoo Finance ticker, fetches fundamentals
(price, market cap, sector, industry, country, P/E, dividends, 52-week range),
and writes them to portfolio.db.

For CDRs, if the NEO listing is missing sector/industry/country, the script
falls back to the underlying company ticker. For ETFs it applies keyword-based
classifications (e.g. gold/uranium -> Basic Materials) and infers a domicile /
holdings country.

Ticker resolution (no lookup table, rule-based):
- USD securities: plain ticker (ACHR, GLD, TBIL)
- CDRs: {symbol}.NE first (actual CDR), then the underlying {symbol}
- CAD stocks/ETFs: {symbol}.TO, then .V, then .CN, then plain

Usage:
    python fetch_security_info.py                  # update missing only
    python fetch_security_info.py --dry-run        # preview, no writes
    python fetch_security_info.py --force          # refresh everything
    python fetch_security_info.py --delay 0.5      # slower rate limit
"""

import argparse
import re
import time
from datetime import date
from pathlib import Path
from typing import Optional

from config import DB_PATH
from database import get_connection, migrate_securities_schema


# Country lookup by Yahoo Finance exchange code. Used as a fallback when
# yfinance does not populate the `country` field (common for ETFs).
EXCHANGE_COUNTRY_MAP = {
    "TOR": "Canada",
    "NEO": "Canada",
    "V": "Canada",
    "CN": "Canada",
    "CNSX": "Canada",
    "TSX": "Canada",
    "NYQ": "United States",
    "NMS": "United States",
    "PCX": "United States",
    "NGM": "United States",
    "NYSE": "United States",
    "NASDAQ": "United States",
    "BATS": "United States",
    "ARCA": "United States",
    "LSE": "United Kingdom",
    "LON": "United Kingdom",
    "FRA": "Germany",
    "GER": "Germany",
    "HKG": "Hong Kong",
    "JPX": "Japan",
    "JAS": "Japan",
    "ASX": "Australia",
    "TSN": "Taiwan",
    "TWO": "Taiwan",
    "NSE": "India",
    "BSE": "India",
}


# Keywords that signal a globally diversified international ETF.
INTERNATIONAL_ETF_KEYWORDS = [
    "GLOBAL",
    "INTERNATIONAL",
    "WORLD",
    "EAFE",
    "EMERGING",
    "MSCI",
    "ACWI",
    "ALL COUNTRY",
    "DEVELOPED",
    "EX-US",
    "EX US",
    "FOREIGN",
]


def resolve_ticker(symbol: str, currency: str, is_cdr: int) -> list[str]:
    """Return candidate Yahoo Finance tickers in preference order."""
    if currency == "USD":
        return [symbol]
    if is_cdr:
        # CDRs list on NEO (.NE). The underlying company is the plain symbol.
        return [f"{symbol}.NE", symbol]
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


def _combined_text(info: dict) -> str:
    """Upper-case name + category for keyword matching."""
    name = info.get("longName") or info.get("shortName") or ""
    category = info.get("category") or ""
    return f"{name} {category}".upper()


def infer_etf_sector_industry(info: dict) -> tuple[Optional[str], Optional[str]]:
    """Return (sector, industry) for an ETF based on its name/category."""
    text = _combined_text(info)

    if any(k in text for k in ["GOLD", "SILVER", "PRECIOUS METAL"]):
        return "Basic Materials", "Precious Metals"
    if any(k in text for k in ["URANIUM", "NUCLEAR"]):
        return "Basic Materials", "Uranium"
    if any(k in text for k in ["COMMODITY", "NATURAL RESOURCES"]):
        return "Basic Materials", None
    if any(k in text for k in ["BOND", "T-BILL", "TREASURY", "FIXED INCOME", "SAVINGS", "HIGH INTEREST", "MONEY MARKET", "ULTRASHORT"]):
        return "Fixed Income", None
    if any(k in text for k in ["CURRENCY", "DOLLAR", "FOREX"]):
        return "Currency", "Currency"
    if any(k in text for k in ["REAL ESTATE", " REIT"]):
        return "Real Estate", "Real Estate"
    if any(k in text for k in ["ENERGY", "OIL", "GAS"]):
        return "Energy", "Energy"
    if any(k in text for k in ["UTILITIES"]):
        return "Utilities", "Utilities"
    if any(k in text for k in ["INFRASTRUCTURE"]):
        return "Industrials", "Infrastructure"
    if any(k in text for k in ["TECHNOLOGY", "TECH ", "SEMICONDUCTOR"]):
        return "Technology", "Technology"
    if any(k in text for k in ["FINANCIAL", "BANK"]):
        return "Financial Services", "Financials"
    if any(k in text for k in ["HEALTH CARE", "HEALTHCARE", "BIOTECH", "PHARMA"]):
        return "Healthcare", "Healthcare"
    if any(k in text for k in ["INDEX", "NASDAQ", "S&P", "DOW", "RUSSELL", "EQUITY", "STOCK", "SOCIAL"]):
        return "Equities", None

    # Fall back to the ETF category as a sector if no specific keyword matched.
    category = info.get("category")
    if category:
        return category, None
    return None, None


def infer_etf_country(info: dict) -> Optional[str]:
    """Infer a country for an ETF from its name/exchange."""
    name = (info.get("longName") or info.get("shortName") or "").upper()
    exchange = (info.get("exchange") or "").upper()

    # "Global X" is a Canadian fund family, not an international mandate.
    name_clean = re.sub(r"\bGLOBAL\s*X\b", "", name).strip()
    if any(k in name_clean for k in INTERNATIONAL_ETF_KEYWORDS):
        return "International"

    if any(k in name_clean for k in ["CANADIAN", "CANADA", "S&P/TSX", "TSX"]):
        return "Canada"
    if any(k in name_clean for k in ["U.S.", "US ", "USA", "NASDAQ", "S&P 500", "RUSSELL", "DOW"]):
        return "United States"
    if any(k in name_clean for k in ["EUROPE", "EURO", "EUROZONE"]):
        return "Europe"
    if any(k in name_clean for k in ["CHINA", "CHINESE"]):
        return "China"

    return EXCHANGE_COUNTRY_MAP.get(exchange)


def infer_country(info: dict) -> Optional[str]:
    """Best-effort country from yfinance info, falling back to exchange map."""
    country = info.get("country")
    if country:
        return country
    exchange = (info.get("exchange") or "").upper()
    return EXCHANGE_COUNTRY_MAP.get(exchange)


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
                "SELECT id, symbol, currency, is_cdr, asset_class FROM securities "
                "WHERE is_cash = 0 OR is_cash IS NULL"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, symbol, currency, is_cdr, asset_class FROM securities "
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

            # For CDRs, fill missing sector/industry/country from the underlying company.
            if row["is_cdr"]:
                missing = not (info.get("sector") and info.get("industry") and info.get("country"))
                if missing:
                    underlying = fetch_info(row["symbol"])
                    if underlying:
                        for key in ("sector", "industry", "country"):
                            if not info.get(key):
                                info[key] = underlying.get(key)

            # For ETFs, derive sector/industry/country when yfinance leaves them blank.
            if row["asset_class"] == "etf":
                if not info.get("sector"):
                    sector, industry = infer_etf_sector_industry(info)
                    if sector:
                        info["sector"] = sector
                    if industry:
                        info["industry"] = industry
                if not info.get("country"):
                    info["country"] = infer_etf_country(info)

            name = pick_name(info, row["is_cdr"])
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            values = {
                "last_price": price,
                "last_price_date": date.today().isoformat(),
                "market_cap": info.get("marketCap"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "country": infer_country(info),
                "description": name,
                "trailing_pe": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "dividend_yield": info.get("dividendYield"),
                "dividend_rate": info.get("dividendRate"),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            }

            sector = values["sector"] or "n/a"
            country = values["country"] or "n/a"
            if dry_run:
                print(f"  {row['symbol']:8} -> {used_ticker:12} {str(name)[:35]:35} price={price} sector={sector} country={country} (dry run)")
            else:
                conn.execute(
                    """
                    UPDATE securities SET
                        last_price = ?,
                        last_price_date = ?,
                        market_cap = ?,
                        sector = ?,
                        industry = ?,
                        country = ?,
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
                        values["country"],
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
                print(f"  {row['symbol']:8} -> {used_ticker:12} {str(name)[:35]:35} price={price} sector={sector} country={country}")
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
