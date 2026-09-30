"""Tests for holdings.md auto-sync."""

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from holdings_md import (
    format_ticker,
    get_current_holdings,
    render_ticker_lines,
    sync_holdings_md,
)


def _make_db(path: Path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE securities (
            id INTEGER PRIMARY KEY, symbol TEXT, name TEXT, currency TEXT,
            is_cdr INTEGER DEFAULT 0, exchange TEXT,
            is_cash INTEGER DEFAULT 0, is_benchmark INTEGER DEFAULT 0
        );
        CREATE TABLE holdings (
            id INTEGER PRIMARY KEY, account_id INTEGER, security_id INTEGER,
            quantity REAL, avg_cost REAL, total_cost_basis REAL,
            first_purchase_date TEXT, last_transaction_date TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO securities (id, symbol, name, currency, is_cdr, exchange)"
        " VALUES (1, 'SHOP', 'Shopify', 'CAD', 0, NULL)"
    )
    conn.execute(
        "INSERT INTO securities (id, symbol, name, currency, is_cdr, exchange)"
        " VALUES (2, 'NVDA', 'Nvidia CDR (CAD Hedged)', 'CAD', 1, 'NEO')"
    )
    conn.execute(
        "INSERT INTO securities (id, symbol, name, currency, is_cdr, exchange)"
        " VALUES (3, 'FN', 'Fabrinet', 'USD', 0, NULL)"
    )
    conn.execute(
        "INSERT INTO securities (id, symbol, name, currency, is_cdr, exchange,"
        " is_cash) VALUES (4, 'CASH-CAD', 'Cash CAD', 'CAD', 0, NULL, 1)"
    )
    conn.execute(
        "INSERT INTO holdings (account_id, security_id, quantity, avg_cost,"
        " total_cost_basis) VALUES (1, 1, 10, 100, 1000)"
    )
    conn.execute(
        "INSERT INTO holdings (account_id, security_id, quantity, avg_cost,"
        " total_cost_basis) VALUES (1, 2, 5, 27, 135)"
    )
    conn.execute(
        "INSERT INTO holdings (account_id, security_id, quantity, avg_cost,"
        " total_cost_basis) VALUES (1, 3, 2, 500, 1000)"
    )
    conn.execute(
        "INSERT INTO holdings (account_id, security_id, quantity, avg_cost,"
        " total_cost_basis) VALUES (1, 4, 100, 1, 100)"
    )
    conn.commit()
    conn.close()


class HoldingsMdTests(unittest.TestCase):
    def test_format_ticker(self):
        self.assertEqual(format_ticker("SHOP", "CAD", 0, None), "TSX:SHOP")
        self.assertEqual(format_ticker("HMM.A", "CAD", 0, None), "TSX:HMM.A")
        self.assertEqual(format_ticker("NVDA", "CAD", 1, "NEO"), "NEO:NVDA")
        self.assertEqual(format_ticker("FN", "USD", 0, None), "FN")

    def test_cash_excluded(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            _make_db(db)
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            try:
                holdings = get_current_holdings(conn)
            finally:
                conn.close()
            symbols = [h["symbol"] for h in holdings]
            self.assertEqual(symbols, ["FN", "NVDA", "SHOP"])
            lines = render_ticker_lines(holdings)
            self.assertIn("- TSX:SHOP — Shopify", lines)
            self.assertIn("- NEO:NVDA — Nvidia CDR (CAD Hedged)", lines)
            self.assertIn("- FN — Fabrinet", lines)

    def test_sync_preserves_notes(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            md = Path(tmp) / "holdings.md"
            _make_db(db)
            md.write_text(
                "# Holdings\n\n## Tickers\n\n- TSX:OLD — Old\n\n## Notes\n\nKeep this.\n",
                encoding="utf-8",
            )
            result = sync_holdings_md(db, md)
            self.assertEqual(result["tickers"], 3)
            text = md.read_text(encoding="utf-8")
            self.assertNotIn("TSX:OLD", text)
            self.assertIn("- TSX:SHOP — Shopify", text)
            self.assertIn("Keep this.", text)
            self.assertIn("Auto-generated", text)

    def test_refresh_hook_rewrites_md(self):
        # refresh_holdings() must rewrite holdings.md every time it runs.
        import refresh_holdings as rh

        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            md = Path(tmp) / "holdings.md"
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            conn.executescript(
                """
                CREATE TABLE brokerages (id INTEGER PRIMARY KEY, name TEXT);
                CREATE TABLE accounts (id INTEGER PRIMARY KEY, brokerage_id INTEGER, account_type TEXT, currency TEXT);
                CREATE TABLE securities (id INTEGER PRIMARY KEY, symbol TEXT, name TEXT, currency TEXT, asset_class TEXT, exchange TEXT, is_cdr INTEGER DEFAULT 0, is_cash INTEGER DEFAULT 0, is_benchmark INTEGER DEFAULT 0);
                CREATE TABLE transactions (id TEXT PRIMARY KEY, account_id INTEGER, security_id INTEGER, date TEXT, type TEXT, quantity REAL, net_amount REAL, price REAL, currency TEXT);
                CREATE TABLE holdings (id INTEGER PRIMARY KEY, account_id INTEGER, security_id INTEGER, quantity REAL, avg_cost REAL, total_cost_basis REAL, first_purchase_date TEXT, last_transaction_date TEXT);
                """
            )
            conn.execute("INSERT INTO accounts (id, brokerage_id, account_type, currency) VALUES (1, 0, 'tfsa', 'CAD')")
            conn.execute("INSERT INTO securities (id, symbol, name, currency) VALUES (1, 'SHOP', 'Shopify', 'CAD')")
            conn.execute(
                "INSERT INTO transactions (id, account_id, security_id, date, type, quantity, net_amount, price, currency)"
                " VALUES ('a', 1, 1, '2024-01-01', 'buy', 10, -1000, 100, 'CAD')"
            )
            conn.commit()
            conn.close()
            md.write_text("# Holdings\n\n## Tickers\n\n## Notes\n", encoding="utf-8")

            orig_md_path = None
            try:
                import holdings_md as hm

                orig_md_path = hm.HOLDINGS_MD_PATH
                hm.HOLDINGS_MD_PATH = md
                result = rh.refresh_holdings(db)
            finally:
                hm.HOLDINGS_MD_PATH = orig_md_path
            self.assertIn("holdings_md", result)
            self.assertIn("TSX:SHOP", md.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
