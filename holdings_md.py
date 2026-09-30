"""Sync holdings.md tickers from the portfolio database.

holdings.md is the source of truth for the Holdings lane: the pipeline
re-reads it on every run. This module regenerates its ``## Tickers``
section from the materialized ``holdings`` table so the file never goes
stale, and is called automatically every time holdings are refreshed
(see :func:`refresh_holdings.refresh_holdings`).

Ticker mapping (per holdings.md accepted forms):
- CDRs (exchange NEO) -> ``NEO:SYM`` (actual CDR listing)
- CAD non-CDR      -> ``TSX:SYM`` (default Toronto listing)
- USD securities   -> bare ``SYM`` (resolved against US listings first)

Usage:
    python holdings_md.py
    python holdings_md.py --db path/to/portfolio.db --md path/to/holdings.md
"""

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import DB_PATH
from database import get_connection

BASE_DIR = Path(__file__).parent
HOLDINGS_MD_PATH = BASE_DIR / "holdings.md"


def format_ticker(symbol: str, currency: str, is_cdr: int, exchange: Optional[str]) -> str:
    """Map a security to its holdings.md ticker form."""
    symbol = (symbol or "").strip()
    if not symbol:
        return symbol
    if is_cdr or (exchange or "").upper() == "NEO":
        return f"NEO:{symbol}"
    if (currency or "CAD").upper() == "USD":
        return symbol
    return f"TSX:{symbol}"


def get_current_holdings(conn: sqlite3.Connection) -> list[dict]:
    """Return current non-cash, non-benchmark holdings ordered by symbol."""
    rows = conn.execute(
        """
        SELECT s.symbol, s.name, s.currency, s.is_cdr, s.exchange
        FROM holdings h
        JOIN securities s ON h.security_id = s.id
        WHERE (s.is_cash = 0 OR s.is_cash IS NULL)
          AND (s.is_benchmark = 0 OR s.is_benchmark IS NULL)
          AND ABS(h.quantity) > 1e-9
        ORDER BY s.symbol
        """
    ).fetchall()
    return [dict(r) for r in rows]


def render_ticker_lines(holdings: list[dict]) -> list[str]:
    """Render ``- TICKER — Name`` lines for the Tickers section."""
    lines = []
    for h in holdings:
        ticker = format_ticker(h["symbol"], h.get("currency") or "CAD",
                               h.get("is_cdr") or 0, h.get("exchange"))
        name = (h.get("name") or "").strip() or h["symbol"]
        lines.append(f"- {ticker} — {name}")
    return lines


def sync_holdings_md(db_path: Optional[Path] = None,
                     md_path: Optional[Path] = None) -> dict:
    """Regenerate the ``## Tickers`` section of holdings.md from the DB.

    Preserves everything outside the Tickers list (header docs, Notes).
    Returns ``{"tickers": n, "path": str}``.
    """
    db_path = db_path or DB_PATH
    md_path = md_path or HOLDINGS_MD_PATH

    conn = get_connection(db_path)
    try:
        holdings = get_current_holdings(conn)
    finally:
        conn.close()

    ticker_lines = render_ticker_lines(holdings)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    auto_comment = (
        f"<!-- Auto-generated from portfolio.db on {stamp} "
        f"({len(ticker_lines)} holdings). "
        "Do not edit this list manually; it is rewritten "
        "every time holdings are refreshed. -->"
    )

    if md_path.exists():
        text = md_path.read_text(encoding="utf-8")
    else:
        text = "# Holdings\n\n## Tickers\n\n## Notes\n"
    lines = text.splitlines()

    def find_heading(name: str) -> Optional[int]:
        for i, line in enumerate(lines):
            if line.strip().lower() == name.lower():
                return i
        return None

    tickers_idx = find_heading("## tickers")
    notes_idx = find_heading("## notes")

    if tickers_idx is None:
        # Append missing sections at the end.
        lines += ["", "## Tickers", ""]
        tickers_idx = len(lines) - 2
        notes_idx = None

    if notes_idx is None or notes_idx < tickers_idx:
        lines += ["", "## Notes", ""]
        notes_idx = len(lines) - 2

    new_lines = (
        lines[: tickers_idx + 1]
        + ["", auto_comment]
        + ticker_lines
        + ["", ""]
        + lines[notes_idx:]
    )
    md_path.write_text("\n".join(new_lines).rstrip("\n") + "\n", encoding="utf-8")
    return {"tickers": len(ticker_lines), "path": str(md_path)}


def main():
    parser = argparse.ArgumentParser(
        description="Regenerate holdings.md tickers from portfolio.db."
    )
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--md", type=Path, default=HOLDINGS_MD_PATH)
    args = parser.parse_args()
    result = sync_holdings_md(args.db, args.md)
    print(f"holdings.md updated: {result['tickers']} tickers -> {result['path']}")


if __name__ == "__main__":
    main()
