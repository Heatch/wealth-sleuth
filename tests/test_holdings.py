"""Tests for holdings refresh, including corporate-action (split) handling."""

import sqlite3
import unittest

from refresh_holdings import refresh_security_holdings


class HoldingsRefreshTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE brokerages (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE accounts (id INTEGER PRIMARY KEY, brokerage_id INTEGER, account_type TEXT, currency TEXT);
            CREATE TABLE securities (
                id INTEGER PRIMARY KEY, symbol TEXT, name TEXT, currency TEXT,
                is_cash INTEGER DEFAULT 0
            );
            CREATE TABLE transactions (
                id TEXT PRIMARY KEY, account_id INTEGER, security_id INTEGER,
                date TEXT, type TEXT, quantity REAL, net_amount REAL, price REAL, currency TEXT
            );
            CREATE TABLE holdings (
                id INTEGER PRIMARY KEY, account_id INTEGER, security_id INTEGER,
                quantity REAL, avg_cost REAL, total_cost_basis REAL,
                first_purchase_date TEXT, last_transaction_date TEXT
            );
            """
        )
        self.conn.execute("INSERT INTO accounts (id, brokerage_id, account_type, currency) VALUES (1, 0, 'tfsa', 'CAD')")
        self.conn.execute(
            "INSERT INTO securities (id, symbol, name, currency) VALUES (1, 'NVDA', 'Nvidia', 'CAD')"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _txn(self, tid, date, ttype, qty, net, security_id=1):
        self.conn.execute(
            "INSERT INTO transactions (id, account_id, security_id, date, type, quantity, net_amount, price, currency) "
            "VALUES (?, 1, ?, ?, ?, ?, ?, 0, 'CAD')",
            (tid, security_id, date, ttype, qty, net),
        )
        self.conn.commit()

    def test_split_increases_quantity_without_cost(self):
        # Buy 1 share, then a 4:1 split ("other" +3 shares). Result: 4 shares.
        self._txn("a", "2024-01-01", "buy", 1, -100)
        self._txn("b", "2024-02-01", "other", 3, 0)
        refresh_security_holdings(self.conn)
        row = self.conn.execute(
            "SELECT quantity, avg_cost, total_cost_basis FROM holdings WHERE security_id=1"
        ).fetchone()
        self.assertAlmostEqual(row["quantity"], 4)
        self.assertAlmostEqual(row["total_cost_basis"], 100)
        self.assertAlmostEqual(row["avg_cost"], 25)

    def test_spinoff_creates_zero_cost_position(self):
        # No prior buy, only a spinoff "other" (+0.3192 shares).
        self._txn("a", "2024-10-02", "other", 0.3192, 0)
        refresh_security_holdings(self.conn)
        row = self.conn.execute(
            "SELECT quantity, total_cost_basis FROM holdings WHERE security_id=1"
        ).fetchone()
        self.assertAlmostEqual(row["quantity"], 0.3192)
        self.assertAlmostEqual(row["total_cost_basis"], 0)

    def test_other_with_cash_ignored_for_shares(self):
        # Regression test (TBIL): "other" rows with nonzero net_amount are
        # cash distributions; their quantity must not change the position.
        # Buy 2, sell 2 -> fully closed, no holding row at all.
        self._txn("a", "2025-03-10", "buy", 2, -99.78)
        self._txn("b", "2026-05-01", "sell", -2, 99.72)
        self._txn("c", "", "other", 2, 0.05)
        self._txn("d", "", "other", 2, -0.30)
        refresh_security_holdings(self.conn)
        row = self.conn.execute(
            "SELECT quantity FROM holdings WHERE security_id=1"
        ).fetchone()
        self.assertIsNone(row)

    def test_spinoff_reallocates_parent_basis(self):
        # TRP -> SOBO (Oct 2024): 9% of TRP's $100 cost moves to SOBO.
        self.conn.execute(
            "INSERT INTO securities (id, symbol, name, currency) VALUES (2, 'TRP', 'TC Energy', 'CAD')"
        )
        self.conn.execute(
            "INSERT INTO securities (id, symbol, name, currency) VALUES (3, 'SOBO', 'South Bow', 'CAD')"
        )
        self.conn.commit()
        self._txn("a", "2024-09-03", "buy", 1.5961, -100.0, security_id=2)
        self._txn("b", "2024-10-02", "other", 0.3192, 0.0, security_id=3)
        refresh_security_holdings(self.conn)
        trp = self.conn.execute(
            "SELECT quantity, total_cost_basis FROM holdings WHERE security_id=2"
        ).fetchone()
        self.assertAlmostEqual(trp["quantity"], 1.5961)
        self.assertAlmostEqual(trp["total_cost_basis"], 91.0, places=2)
        sobo = self.conn.execute(
            "SELECT quantity, total_cost_basis FROM holdings WHERE security_id=3"
        ).fetchone()
        self.assertAlmostEqual(sobo["quantity"], 0.3192)
        self.assertAlmostEqual(sobo["total_cost_basis"], 9.0, places=2)


if __name__ == "__main__":
    unittest.main()
