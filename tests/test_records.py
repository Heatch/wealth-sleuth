"""Tests for all-time best/worst performer records."""

import sqlite3
import unittest

from api.services.records import compute_records, top_records


class RecordsTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE brokerages (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE accounts (id INTEGER PRIMARY KEY, brokerage_id INTEGER, account_type TEXT);
            CREATE TABLE securities (
                id INTEGER PRIMARY KEY, symbol TEXT, name TEXT, description TEXT,
                currency TEXT, sector TEXT, country TEXT, last_price REAL
            );
            CREATE TABLE transactions (
                id TEXT PRIMARY KEY, account_id INTEGER, security_id INTEGER,
                date TEXT, type TEXT, quantity REAL, net_amount REAL,
                price REAL, currency TEXT
            );
            CREATE TABLE fx_history (date TEXT PRIMARY KEY, rate REAL);
            """
        )
        self.conn.execute("INSERT INTO brokerages (id, name) VALUES (1, 'wealthsimple')")
        self.conn.execute(
            "INSERT INTO accounts (id, brokerage_id, account_type) VALUES (1, 1, 'tfsa')"
        )
        self.conn.execute(
            "INSERT INTO securities (id, symbol, name, currency, last_price) VALUES (1, 'AAA', 'Alpha', 'CAD', 150.0)"
        )
        self.conn.execute(
            "INSERT INTO securities (id, symbol, name, currency, last_price) VALUES (2, 'BBB', 'Beta', 'CAD', 50.0)"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _txn(self, tid, security_id, date, ttype, qty, net_amount, price=None, currency="CAD"):
        self.conn.execute(
            "INSERT INTO transactions (id, account_id, security_id, date, type, quantity, net_amount, price, currency) "
            "VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)",
            (tid, security_id, date, ttype, qty, net_amount, price, currency),
        )
        self.conn.commit()

    def test_closed_trade_gain(self):
        # Buy 10 @ $100, sell 10 @ $150 -> +$500, +50%
        self._txn("a", 1, "2024-01-01", "buy", 10, -1000, 100)
        self._txn("b", 1, "2024-06-01", "sell", -10, 1500, 150)
        records = compute_records(self.conn)
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertFalse(r["is_open"])
        self.assertAlmostEqual(r["gain_amount"], 500)
        self.assertAlmostEqual(r["gain_pct"], 0.5)

    def test_open_position_gain(self):
        # Buy 10 @ $100, still holding, last_price $150 -> +$500 unrealized.
        self._txn("a", 1, "2024-01-01", "buy", 10, -1000, 100)
        records = compute_records(self.conn)
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertTrue(r["is_open"])
        self.assertIsNone(r["sell_date"])
        self.assertAlmostEqual(r["gain_amount"], 500)
        self.assertAlmostEqual(r["gain_pct"], 0.5)

    def test_fifo_matching(self):
        # Buy 10 @ $100, buy 10 @ $200, sell 10 @ $150 -> closes first lot.
        self._txn("a", 1, "2024-01-01", "buy", 10, -1000, 100)
        self._txn("b", 1, "2024-02-01", "buy", 10, -2000, 200)
        self._txn("c", 1, "2024-03-01", "sell", -10, 1500, 150)
        records = compute_records(self.conn)
        # One closed record (first lot) + one open record (second lot).
        self.assertEqual(len(records), 2)
        closed = [r for r in records if not r["is_open"]][0]
        self.assertAlmostEqual(closed["gain_amount"], 500)
        open_rec = [r for r in records if r["is_open"]][0]
        self.assertAlmostEqual(open_rec["buy_price"], 200)

    def test_top_and_worst(self):
        # AAA: +500 gain (best). BBB: -250 loss (worst).
        self._txn("a", 1, "2024-01-01", "buy", 10, -1000, 100)
        self._txn("b", 1, "2024-06-01", "sell", -10, 1500, 150)
        self._txn("c", 2, "2024-01-01", "buy", 10, -500, 50)
        self._txn("d", 2, "2024-06-01", "sell", -10, 250, 25)
        result = top_records(self.conn, sort_by="amount", top_n=10)
        self.assertEqual(result["best"][0]["symbol"], "AAA")
        self.assertEqual(result["worst"][0]["symbol"], "BBB")

    def test_zero_cost_basis_excluded(self):
        # Transfer-in at $0 cost basis should not appear as a performer.
        self._txn("a", 1, "2024-01-01", "transfer", 10, 0, 0)
        result = top_records(self.conn, sort_by="amount", top_n=10)
        self.assertEqual(result["best"], [])
        self.assertEqual(result["worst"], [])

    def test_split_scales_cost_basis(self):
        # Buy 4 @ $100, then a 3:1 split ("other" +8 shares). Cost per share
        # should drop to $33.33 and quantity become 12, with no phantom gain.
        self._txn("a", 1, "2024-01-01", "buy", 4, -400, 100)
        self._txn("b", 1, "2024-02-01", "other", 8, 0, 0)
        records = compute_records(self.conn)
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertTrue(r["is_open"])
        self.assertAlmostEqual(r["quantity"], 12)
        self.assertAlmostEqual(r["buy_price"], 400 / 12)

    def test_consolidation_multiple_buys(self):
        # Multiple buys of the same symbol collapse into a single open record.
        self._txn("a", 1, "2024-01-01", "buy", 10, -1000, 100)
        self._txn("b", 1, "2024-03-01", "buy", 10, -2000, 200)
        records = compute_records(self.conn)
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertTrue(r["is_open"])
        self.assertAlmostEqual(r["quantity"], 20)
        self.assertAlmostEqual(r["buy_price"], 150)  # (1000+2000)/20
        self.assertEqual(r["buy_date"], "2024-01-01")

    def test_other_with_cash_ignored_for_shares(self):
        # Regression test (TBIL): an "other" row with a nonzero net_amount is
        # a cash distribution whose quantity column repeats the position size.
        # It must not create phantom shares. Buy 2, sell 2, plus two cash
        # "other" rows -> single flat closed record, no open record.
        self._txn("a", 1, "2025-03-10", "buy", 2, -99.78, 49.89)
        self._txn("b", 1, "2026-05-01", "sell", -2, 99.72, 49.8644)
        self._txn("c", 1, "2026-09-26", "other", 2, 0.05, 0)
        self._txn("d", 1, "2026-09-26", "other", 2, -0.30, 0)
        records = compute_records(self.conn)
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertFalse(r["is_open"])
        self.assertAlmostEqual(r["quantity"], 2)
        self.assertAlmostEqual(r["gain_amount"], -0.06, places=2)

    def test_spinoff_reallocates_parent_basis(self):
        # TRP -> SOBO (Oct 2024): 9% of TRP's $100 cost moves to the 0.3192
        # SOBO shares; TRP keeps 91%. Neither leg is measured off $0.
        self.conn.execute(
            "INSERT INTO securities (id, symbol, name, currency, last_price) VALUES (3, 'TRP', 'TC Energy', 'CAD', 83.17)"
        )
        self.conn.execute(
            "INSERT INTO securities (id, symbol, name, currency, last_price) VALUES (4, 'SOBO', 'South Bow', 'CAD', 48.08)"
        )
        self.conn.commit()
        self._txn("a", 3, "2024-09-03", "buy", 1.5961, -100.0, 62.65)
        self._txn("b", 4, "2024-10-02", "other", 0.3192, 0.0, 0)
        records = {r["symbol"]: r for r in compute_records(self.conn)}
        sobo = records["SOBO"]
        self.assertTrue(sobo["is_open"])
        self.assertAlmostEqual(sobo["cost_basis"], 9.0, places=2)
        self.assertAlmostEqual(sobo["gain_amount"], 0.3192 * 48.08 - 9.0, places=2)
        trp = records["TRP"]
        self.assertTrue(trp["is_open"])
        self.assertAlmostEqual(trp["cost_basis"], 91.0, places=2)


if __name__ == "__main__":
    unittest.main()
