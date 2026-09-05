"""
Demo Portfolio UI for Portfolio Tracker.

Reads current holdings directly from portfolio.db and generates a
self-contained portfolio.html. No web server needed — just open the
HTML file in a browser.

Columns: company name, ticker, brokerage, account, shares held,
avg cost, invested (cost basis), value, gain/loss.

All money values are shown in CAD. USD-denominated holdings are converted
at the current USD->CAD rate from yfinance (USDCAD=X).

Value and gain/loss require live prices (securities.last_price) — those
cells show "—" until price data exists.

Usage:
    python demo_ui.py
    python demo_ui.py --db path/to/portfolio.db --out path/to/portfolio.html
    python demo_ui.py --fx-rate 1.38   # manual rate (offline fallback)
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


def get_usd_to_cad(fx_override=None) -> tuple[float, str]:
    """Get the current USD->CAD rate.

    Returns (rate, source). Uses --fx-rate override when given,
    otherwise fetches USDCAD=X from yfinance.
    """
    if fx_override is not None:
        return fx_override, "manual --fx-rate"
    import yfinance as yf

    info = yf.Ticker("USDCAD=X").info
    rate = info.get("regularMarketPrice") or info.get("currentPrice")
    if not rate:
        raise RuntimeError(
            "Could not fetch USDCAD=X from yfinance. "
            "Pass --fx-rate explicitly (e.g. --fx-rate 1.38)."
        )
    return rate, "yfinance USDCAD=X"


def build_html(holdings: list[dict], usd_to_cad: float, fx_source: str) -> str:
    """Build the holdings page HTML. All money values converted to CAD."""
    securities = [h for h in holdings if not h["is_cash"]]
    cash = [h for h in holdings if h["is_cash"]]

    def to_cad(h: dict, field: str):
        """Convert a money field to CAD using the holding's currency."""
        value = h[field]
        if value is None:
            return None
        if h["currency"] == "USD":
            return value * usd_to_cad
        return value

    def value_of(h: dict):
        if h["last_price"] is None:
            return None
        raw_value = h["quantity"] * h["last_price"]
        if h["currency"] == "USD":
            return raw_value * usd_to_cad
        return raw_value

    def gain_of(h: dict):
        value = value_of(h)
        if value is None:
            return None
        return value - to_cad(h, "cost_basis")

    def row_html(h: dict, convert_qty: bool = False) -> str:
        value = value_of(h)
        gain = gain_of(h)
        gain_cls = ""
        if gain is not None:
            gain_cls = "gain-pos" if gain >= 0 else "gain-neg"
        qty = h["quantity"]
        if convert_qty and qty is not None and h["currency"] == "USD":
            qty = qty * usd_to_cad
        return (
            "<tr>"
            f"<td>{esc(h['name'])}</td>"
            f"<td><code>{esc(h['symbol'])}</code></td>"
            f"<td>{esc(h['brokerage'])}</td>"
            f"<td>{esc(h['account'])}</td>"
            f"<td class='num'>{fmt_qty(qty)}</td>"
            f"<td class='num'>{fmt_money(to_cad(h, 'avg_cost'))}</td>"
            f"<td class='num'>{fmt_money(to_cad(h, 'cost_basis'))}</td>"
            f"<td class='num'>{fmt_money(value)}</td>"
            f"<td class='num {gain_cls}'>{fmt_money(gain)}</td>"
            "</tr>"
        )

    security_rows = "\n".join(row_html(h) for h in securities)
    cash_rows = "\n".join(row_html(h, convert_qty=True) for h in cash)

    invested = sum(to_cad(h, "cost_basis") or 0 for h in securities)
    priced_value = sum(v for h in securities if (v := value_of(h)) is not None)
    priced_gain = sum(g for h in securities if (g := gain_of(h)) is not None)
    has_prices = any(h["last_price"] is not None for h in securities)
    def cash_cad(h: dict) -> float:
        qty = h["quantity"] or 0
        return qty * usd_to_cad if h["currency"] == "USD" else qty

    cash_total = sum(cash_cad(h) for h in cash)

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
&middot; {len(cash)} cash balances &middot; all values in CAD
&middot; USD&rarr;CAD {usd_to_cad:.4f} ({esc(fx_source)})</p>
{price_note}

<h2>Securities</h2>
<table>
<thead>
<tr><th>Name</th><th>Ticker</th><th>Brokerage</th><th>Account</th>
<th>Shares</th><th>Avg Cost (CAD)</th><th>Invested (CAD)</th><th>Value (CAD)</th><th>Gain/Loss (CAD)</th></tr>
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
<th>Balance (CAD)</th><th>Avg Cost (CAD)</th><th>Invested (CAD)</th><th>Value (CAD)</th><th>Gain/Loss (CAD)</th></tr>
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
    parser.add_argument(
        "--fx-rate",
        type=float,
        default=None,
        help="Manual USD->CAD rate (default: fetch USDCAD=X from yfinance)",
    )

    args = parser.parse_args()

    if not args.db.exists():
        print(f"Database not found: {args.db}")
        print("Run `python consolidate.py` first.")
        return

    usd_to_cad, fx_source = get_usd_to_cad(args.fx_rate)
    print(f"USD->CAD: {usd_to_cad:.4f} ({fx_source})")

    holdings = fetch_holdings(args.db)
    args.out.write_text(
        build_html(holdings, usd_to_cad, fx_source), encoding="utf-8"
    )
    print(f"Wrote {len(holdings)} holdings to: {args.out}")
    print("Open it in a browser to view.")


if __name__ == "__main__":
    main()
