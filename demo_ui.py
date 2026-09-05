"""
Demo Portfolio UI for Portfolio Tracker.

Reads current holdings directly from portfolio.db and generates a
self-contained portfolio.html. No web server needed — just open the
HTML file in a browser.

Columns: company name, ticker, brokerage, account, shares held,
avg cost, invested (cost basis), value, gain/loss.

Value and gain/loss require live prices (securities.last_price), which
are not populated yet — those cells show "—" until price data exists.

Usage:
    python demo_ui.py
    python demo_ui.py --db path/to/portfolio.db --out path/to/portfolio.html
"""

import argparse
import html
import sqlite3
from datetime import datetime
from pathlib import Path

from config import BASE_DIR, DB_PATH


def fetch_holdings(db_path: Path) -> list[dict]:
    """Fetch all holdings with security/account/brokerage details."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                s.name AS name,
                s.symbol AS symbol,
                s.currency AS currency,
                s.asset_class AS asset_class,
                s.is_cash AS is_cash,
                s.last_price AS last_price,
                b.name AS brokerage,
                a.account_type AS account,
                h.quantity AS quantity,
                h.avg_cost AS avg_cost,
                h.total_cost_basis AS cost_basis,
                h.first_purchase_date AS first_bought,
                h.last_transaction_date AS last_activity
            FROM holdings h
            JOIN accounts a ON h.account_id = a.id
            JOIN brokerages b ON a.brokerage_id = b.id
            JOIN securities s ON h.security_id = s.id
            ORDER BY ABS(h.total_cost_basis) DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def fmt_money(value) -> str:
    """Format a number as $X,XXX.XX, or em-dash when None."""
    if value is None:
        return "&mdash;"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def fmt_qty(value) -> str:
    """Format share quantity, trimming trailing zeros."""
    if value is None:
        return "&mdash;"
    text = f"{value:,.4f}".rstrip("0").rstrip(".")
    return text if text else "0"


def esc(value) -> str:
    """HTML-escape a value."""
    return html.escape(str(value if value is not None else ""))


def build_html(holdings: list[dict]) -> str:
    """Build the holdings page HTML."""
    securities = [h for h in holdings if not h["is_cash"]]
    cash = [h for h in holdings if h["is_cash"]]

    def value_of(h: dict):
        if h["last_price"] is None:
            return None
        return h["quantity"] * h["last_price"]

    def gain_of(h: dict):
        value = value_of(h)
        if value is None:
            return None
        return value - h["cost_basis"]

    def row_html(h: dict) -> str:
        value = value_of(h)
        gain = gain_of(h)
        gain_cls = ""
        if gain is not None:
            gain_cls = "gain-pos" if gain >= 0 else "gain-neg"
        return (
            "<tr>"
            f"<td>{esc(h['name'])}</td>"
            f"<td><code>{esc(h['symbol'])}</code></td>"
            f"<td>{esc(h['brokerage'])}</td>"
            f"<td>{esc(h['account'])}</td>"
            f"<td class='num'>{fmt_qty(h['quantity'])}</td>"
            f"<td class='num'>{fmt_money(h['avg_cost'])}</td>"
            f"<td class='num'>{fmt_money(h['cost_basis'])}</td>"
            f"<td class='num'>{fmt_money(value)}</td>"
            f"<td class='num {gain_cls}'>{fmt_money(gain)}</td>"
            "</tr>"
        )

    security_rows = "\n".join(row_html(h) for h in securities)
    cash_rows = "\n".join(row_html(h) for h in cash)

    invested = sum(h["cost_basis"] or 0 for h in securities)
    priced_value = sum(v for h in securities if (v := value_of(h)) is not None)
    priced_gain = sum(g for h in securities if (g := gain_of(h)) is not None)
    has_prices = any(h["last_price"] is not None for h in securities)
    cash_total = sum(h["quantity"] or 0 for h in cash)

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    price_note = (
        ""
        if has_prices
        else "<p class='note'>Live prices are not loaded yet "
        "(<code>securities.last_price</code> is empty), so Value and "
        "Gain/Loss show &mdash;. Invested reflects cost basis from the DB.</p>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Portfolio Holdings (Demo)</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 2rem; color: #1a1a1a; }}
  h1 {{ font-size: 1.5rem; }}
  h2 {{ font-size: 1.15rem; margin-top: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.9rem; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
  th {{ background: #f4f4f4; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  code {{ font-size: 0.85em; }}
  .gain-pos {{ color: #0a7a2f; }}
  .gain-neg {{ color: #b3261e; }}
  tfoot td {{ font-weight: bold; background: #fafafa; }}
  .note {{ color: #666; font-size: 0.85rem; }}
  .meta {{ color: #666; font-size: 0.8rem; }}
</style>
</head>
<body>
<h1>Portfolio Holdings (Demo)</h1>
<p class="meta">Generated {generated} &middot; {len(securities)} positions
&middot; {len(cash)} cash balances</p>
{price_note}

<h2>Securities</h2>
<table>
<thead>
<tr><th>Name</th><th>Ticker</th><th>Brokerage</th><th>Account</th>
<th>Shares</th><th>Avg Cost</th><th>Invested</th><th>Value</th><th>Gain/Loss</th></tr>
</thead>
<tbody>
{security_rows}
</tbody>
<tfoot>
<tr><td colspan="6">Total invested (securities)</td>
<td class="num">{fmt_money(invested)}</td>
<td class="num">{fmt_money(priced_value) if has_prices else "&mdash;"}</td>
<td class="num">{fmt_money(priced_gain) if has_prices else "&mdash;"}</td></tr>
</tfoot>
</table>

<h2>Cash</h2>
<table>
<thead>
<tr><th>Name</th><th>Ticker</th><th>Brokerage</th><th>Account</th>
<th>Balance</th><th>Avg Cost</th><th>Invested</th><th>Value</th><th>Gain/Loss</th></tr>
</thead>
<tbody>
{cash_rows}
</tbody>
<tfoot>
<tr><td colspan="4">Total cash</td>
<td class="num">{fmt_qty(cash_total)}</td>
<td colspan="4"></td></tr>
</tfoot>
</table>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(
        description="Generate a demo portfolio holdings page from portfolio.db."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=BASE_DIR / "portfolio.html",
        help="Path to output HTML file",
    )

    args = parser.parse_args()

    if not args.db.exists():
        print(f"Database not found: {args.db}")
        print("Run `python consolidate.py` first.")
        return

    holdings = fetch_holdings(args.db)
    args.out.write_text(build_html(holdings), encoding="utf-8")
    print(f"Wrote {len(holdings)} holdings to: {args.out}")
    print("Open it in a browser to view.")


if __name__ == "__main__":
    main()
