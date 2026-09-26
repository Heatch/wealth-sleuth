"""Tests for TFSA contribution room calculation."""

import sqlite3
import unittest

from api.services.tfsa import (
    annual_limit,
    cumulative_room_to_year,
    first_contribution_year,
    tfsa_summary,
)


class TfsaLimitTests(unittest.TestCase):
    def test_first_contribution_year_after_2009(self):
        self.assertEqual(first_contribution_year(2005), 2023)

    def test_first_contribution_year_before_2009(self):
        # Room only starts in 2009 even if you turned 18 earlier.
        self.assertEqual(first_contribution_year(1980), 2009)

    def test_annual_limit_known_year(self):
        self.assertEqual(annual_limit(2023), 6500)
        self.assertEqual(annual_limit(2015), 10000)

    def test_annual_limit_future_year_fallback(self):
        self.assertEqual(annual_limit(2100), annual_limit(max([2026])))

    def test_cumulative_room_default_birth_year(self):
        # 2005 -> first year 2023 -> 2026 limits: 6500 + 7000 + 7000 + 7000
        self.assertEqual(cumulative_room_to_year(2005, 2026), 27500)


class TfsaSummaryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE accounts (id INTEGER PRIMARY KEY, account_type TEXT, currency TEXT);
            CREATE TABLE transactions (
                id TEXT PRIMARY KEY,
                account_id INTEGER,
                date TEXT,
                type TEXT,
                net_amount REAL,
                currency TEXT
            );
            CREATE TABLE fx_history (
                date TEXT PRIMARY KEY,
                rate REAL
            );
            """
        )
        self.conn.execute(
            "INSERT INTO accounts (id, account_type, currency) VALUES (?, ?, ?)",
            (1, "tfsa", "CAD"),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _deposit(self, date: str, amount: float, currency: str = "CAD"):
        self.conn.execute(
            "INSERT INTO transactions (id, account_id, date, type, net_amount, currency) VALUES (?, ?, ?, ?, ?, ?)",
            (f"d-{date}-{amount}-{currency}", 1, date, "deposit", amount, currency),
        )
        self.conn.commit()

    def _withdraw(self, date: str, amount: float, currency: str = "CAD"):
        self.conn.execute(
            "INSERT INTO transactions (id, account_id, date, type, net_amount, currency) VALUES (?, ?, ?, ?, ?, ?)",
            (f"w-{date}-{amount}-{currency}", 1, date, "withdrawal", amount, currency),
        )
        self.conn.commit()

    def test_no_transactions(self):
        result = tfsa_summary(self.conn, birth_year=2005, current_year=2026)
        self.assertEqual(result["cumulative_room"], 27500)
        self.assertEqual(result["lifetime_contributions"], 0)
        self.assertEqual(result["remaining_room"], 27500)
        self.assertEqual(result["pct_used"], 0)

    def test_contributions_reduce_room(self):
        self._deposit("2026-01-01", 5000)
        result = tfsa_summary(self.conn, birth_year=2005, current_year=2026)
        self.assertEqual(result["lifetime_contributions"], 5000)
        self.assertEqual(result["remaining_room"], 22500)
        self.assertAlmostEqual(result["pct_used"], 5000 / 27500, places=6)

    def test_prior_year_withdrawal_adds_room(self):
        # Contribute full 2023 room, withdraw in 2024, check 2025 room.
        self._deposit("2023-01-01", 6500)
        self._withdraw("2024-01-01", 1000)
        result = tfsa_summary(self.conn, birth_year=2005, current_year=2025)
        # 2023-2025 limits = 6500 + 7000 + 7000 = 20500, plus 1000 re-added = 21500
        self.assertEqual(result["total_room"], 21500)
        self.assertEqual(result["remaining_room"], 15000)
        self.assertEqual(result["withdrawal_room"], 1000)

    def test_current_year_withdrawal_not_yet_re_added(self):
        # Withdrawals in the current year do not create room until next year.
        self._deposit("2026-01-01", 5000)
        self._withdraw("2026-02-01", 1000)
        result = tfsa_summary(self.conn, birth_year=2005, current_year=2026)
        self.assertEqual(result["withdrawal_room"], 0)
        self.assertEqual(result["remaining_room"], 22500)

    def test_only_tfsa_deposits_count(self):
        # Non-deposit transactions should be ignored for room calculation.
        self.conn.execute(
            "INSERT INTO transactions (id, account_id, date, type, net_amount, currency) VALUES (?, ?, ?, ?, ?, ?)",
            ("buy-1", 1, "2026-01-01", "buy", -5000, "CAD"),
        )
        self.conn.commit()
        result = tfsa_summary(self.conn, birth_year=2005, current_year=2026)
        self.assertEqual(result["lifetime_contributions"], 0)

    def test_usd_deposit_converted_to_cad(self):
        # USD TFSA contributions share the same CAD-denominated room.
        self.conn.execute("INSERT INTO fx_history (date, rate) VALUES (?, ?)", ("2026-01-01", 1.35))
        self.conn.commit()
        self._deposit("2026-01-01", 1000, "USD")
        result = tfsa_summary(self.conn, birth_year=2005, current_year=2026)
        self.assertEqual(result["lifetime_contributions"], 1350)
        self.assertEqual(result["remaining_room"], 27500 - 1350)


if __name__ == "__main__":
    unittest.main()
