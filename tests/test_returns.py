"""Tests for the rebuilt return calculations and their API integration."""

import sqlite3
import unittest
from datetime import date, timedelta

from api.cache import cache
from api.services import returns as returns_service
from api.services.fx import convert


def _build_series(start_date: date, values: list[float]) -> list:
    return [
        ((start_date + timedelta(days=i)).isoformat(), v)
        for i, v in enumerate(values)
    ]


class ReturnCalculationTests(unittest.TestCase):
    def test_no_flows_annual_xirr(self):
        """XIRR over exactly one year with no cash flows equals total return."""
        start = date(2024, 1, 1)
        sub = [
            (start.isoformat(), 1000.0),
            ((start + timedelta(days=365)).isoformat(), 1229.0),
        ]
        xirr = returns_service.xirr_return(sub, {})
        self.assertIsNotNone(xirr)
        self.assertAlmostEqual(xirr, 0.229, places=3)

    def test_no_flows_twr_equals_total_return(self):
        """TWR with no cash flows equals simple total return."""
        start = date(2024, 1, 1)
        sub = [
            (start.isoformat(), 1000.0),
            ((start + timedelta(days=365)).isoformat(), 1229.0),
        ]
        twr = returns_service.twr_return(sub, {})
        self.assertIsNotNone(twr)
        self.assertAlmostEqual(twr, 0.229, places=6)

    def test_xirr_with_mid_period_deposit(self):
        """A mid-period deposit makes XIRR differ from TWR."""
        start = date(2024, 1, 1)
        mid = start + timedelta(days=180)
        end = start + timedelta(days=365)
        sub = [
            (start.isoformat(), 1000.0),
            (mid.isoformat(), 1580.0),   # +500 deposit plus 80 growth
            (end.isoformat(), 1700.0),
        ]
        flows = {mid.isoformat(): 500.0}
        xirr = returns_service.xirr_return(sub, flows)
        twr = returns_service.twr_return(sub, flows)
        self.assertIsNotNone(xirr)
        self.assertIsNotNone(twr)
        # The two metrics should not converge when there are external flows.
        self.assertNotAlmostEqual(xirr, twr, places=6)

    def test_point_returns_start_at_zero(self):
        """Point TWR starts at 0%; point XIRR is undefined at the first point."""
        start = date(2024, 1, 1)
        sub = _build_series(start, [1000.0, 1050.0, 1100.0])
        pts = returns_service.point_returns(sub, {})
        self.assertEqual(len(pts), 3)
        self.assertIsNone(pts[0]["xirr"])
        self.assertEqual(pts[0]["twr"], 0.0)
        self.assertAlmostEqual(pts[-1]["twr"], 0.10, places=6)
        self.assertIsNotNone(pts[-1]["xirr"])

    def test_all_period_returns_keys(self):
        """Return package contains all expected periods."""
        start = date(2024, 1, 1)
        sub = _build_series(start, [1000.0, 1050.0, 1100.0, 1200.0])
        result = returns_service.all_period_returns(sub, {})
        self.assertEqual(set(result.keys()), {"1m", "6m", "ytd", "1y", "3y", "all"})


class RealDataIntegrationTests(unittest.TestCase):
    """Run against the real portfolio database to validate filters and caching."""

    @classmethod
    def setUpClass(cls):
        cache.invalidate()
        from database import get_connection
        cls.conn = get_connection()
        cls.accounts = cls.conn.execute(
            "SELECT a.id, b.name AS brokerage FROM accounts a JOIN brokerages b ON a.brokerage_id = b.id"
        ).fetchall()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        cache.invalidate()

    def test_all_accounts_returns_exist(self):
        result = returns_service.portfolio_returns_cached("CAD", None)
        self.assertIn("periods", result)
        self.assertIn("history", result)
        for p in returns_service.PERIODS:
            with self.subTest(period=p):
                pr = result["periods"][p]
                self.assertIn("xirr", pr)
                self.assertIn("twr", pr)
                hist = result["history"][p]
                if hist:
                    self.assertIn("return_xirr", hist[-1])
                    self.assertIn("return_twr", hist[-1])
                    self.assertIn("net_deposits", hist[-1])

    def test_disnat_filter_returns_exist(self):
        disnat_ids = [r["id"] for r in self.accounts if r["brokerage"].lower() == "disnat"]
        if not disnat_ids:
            self.skipTest("No Disnat accounts in database")
        result = returns_service.portfolio_returns_cached("CAD", disnat_ids)
        for p in returns_service.PERIODS:
            with self.subTest(period=p):
                pr = result["periods"][p]
                self.assertIn("xirr", pr)
                self.assertIn("twr", pr)
                # The toggle should always be meaningful, so both values must be present
                # when the period has enough data.
                if result["history"][p]:
                    self.assertIsNotNone(pr["xirr"])
                    self.assertIsNotNone(pr["twr"])

    def test_caching_is_shared(self):
        """The same cached object is returned for identical parameters."""
        first = returns_service.portfolio_returns_cached("CAD", None)
        second = returns_service.portfolio_returns_cached("CAD", None)
        self.assertIs(first, second)

    def test_usd_currency_returns_exist(self):
        result = returns_service.portfolio_returns_cached("USD", None)
        for p in returns_service.PERIODS:
            with self.subTest(period=p):
                self.assertIn("xirr", result["periods"][p])
                self.assertIn("twr", result["periods"][p])


if __name__ == "__main__":
    unittest.main()
