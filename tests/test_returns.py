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

    def test_linked_twr_ignores_later_contributions(self):
        """A later purchase must not be counted as investment performance."""
        dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
        # Day 3 is a buy at an unchanged price (0% that day). Price then rises 10%.
        daily = {
            "2024-01-02": 0.0,
            "2024-01-03": 0.10,
            "2024-01-04": 0.0,
            "2024-01-05": 0.10,
        }
        twr = returns_service.linked_twr(dates, daily)
        self.assertAlmostEqual(twr, 1.10 * 1.10 - 1.0, places=6)
        # (end 242 - start 100) / 100 would be +142% if the second buy counted.
        self.assertLess(twr, 0.25)

    def test_xirr_does_not_double_count_opening_flow(self):
        """A deposit already inside the opening value is not applied again."""
        start = date(2024, 1, 1)
        end = start + timedelta(days=31)
        sub = [(start.isoformat(), 1100.0), (end.isoformat(), 1100.0)]
        flows = {start.isoformat(): 100.0}
        xirr = returns_service.xirr_return(sub, flows)
        self.assertIsNotNone(xirr)
        self.assertAlmostEqual(xirr, 0.0, places=4)


class ValuationEngineTests(unittest.TestCase):
    """In-memory checks for cash-flow dating and slice performance."""

    def setUp(self):
        from api.cache import cache
        cache.invalidate()

    def tearDown(self):
        from api.cache import cache
        cache.invalidate()

    def _conn(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE securities (
                id INTEGER PRIMARY KEY, symbol TEXT, currency TEXT, is_cash INTEGER
            );
            CREATE TABLE price_history (
                security_id INTEGER, date TEXT, close_price REAL, currency TEXT
            );
            CREATE TABLE fx_history (date TEXT PRIMARY KEY, rate REAL);
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY,
                date TEXT,
                settlement_date TEXT,
                type TEXT,
                quantity REAL,
                net_amount REAL,
                currency TEXT,
                security_id INTEGER,
                account_id INTEGER
            );
            """
        )
        return conn

    def test_blank_trade_date_uses_settlement_date(self):
        """Disnat contributions have no trade date; they must not be one flat opening deposit."""
        from api.services.valuation import daily_portfolio_values

        conn = self._conn()
        conn.execute(
            "INSERT INTO transactions VALUES (1, '', '2024-08-13', 'deposit', 50, 50, 'CAD', NULL, 1)"
        )
        conn.execute(
            "INSERT INTO transactions VALUES (2, '', '2024-12-03', 'deposit', 100, 100, 'CAD', NULL, 1)"
        )
        series, _flows, _cash, _base, undated_dep, deposits, _daily = daily_portfolio_values(conn, "CAD")
        conn.close()
        self.assertAlmostEqual(undated_dep, 0.0, places=4)
        self.assertAlmostEqual(deposits.get("2024-08-13", 0.0), 50.0, places=4)
        self.assertAlmostEqual(deposits.get("2024-12-03", 0.0), 100.0, places=4)
        self.assertAlmostEqual(series[0][1], 50.0, places=4)
        self.assertAlmostEqual(series[-1][1], 150.0, places=4)

    def test_slice_twr_excludes_later_buys(self):
        """A second purchase increases value but not the time-weighted return that day."""
        from api.services.valuation import daily_portfolio_values

        conn = self._conn()
        conn.execute("INSERT INTO securities VALUES (1, 'ABC', 'CAD', 0)")
        prices = [
            ("2024-01-01", 10.0),
            ("2024-01-02", 10.0),
            ("2024-01-03", 11.0),
            ("2024-01-04", 11.0),
            ("2024-01-05", 12.1),
        ]
        for d, px in prices:
            conn.execute(
                "INSERT INTO price_history VALUES (1, ?, ?, 'CAD')", (d, px)
            )
        conn.execute(
            "INSERT INTO transactions VALUES (1, '2024-01-02', '2024-01-02', 'buy', 10, -100, 'CAD', 1, 1)"
        )
        conn.execute(
            "INSERT INTO transactions VALUES (2, '2024-01-04', '2024-01-04', 'buy', 10, -110, 'CAD', 1, 1)"
        )
        series, flows, *_rest, daily = daily_portfolio_values(conn, "CAD", None, [1])
        conn.close()
        by_date = dict(series)
        self.assertAlmostEqual(by_date["2024-01-02"], 100.0, places=4)
        self.assertAlmostEqual(by_date["2024-01-04"], 220.0, places=4)
        self.assertAlmostEqual(by_date["2024-01-05"], 242.0, places=4)
        self.assertAlmostEqual(daily["2024-01-04"], 0.0, places=4)
        self.assertAlmostEqual(daily["2024-01-05"], 0.10, places=4)
        twr = returns_service.linked_twr([d for d, _ in series if d >= "2024-01-02"], daily)
        self.assertAlmostEqual(twr, 0.21, places=4)
        naive = (by_date["2024-01-05"] - by_date["2024-01-02"]) / by_date["2024-01-02"]
        self.assertGreater(naive, 1.0)
        self.assertLess(twr, 0.5)

    def test_market_data_cache_shared_and_invalidated(self):
        """The shared price-map cache serves one copy until prices update.

        Repeated loads share the same object; after an invalidation (as
        triggered by price updates) the next load rebuilds from the database.
        """
        from api.cache import cache
        from api.services.valuation import load_market_data_cached

        conn = self._conn()
        conn.execute("INSERT INTO price_history VALUES (1, '2024-01-01', 10.0, 'CAD')")
        m1 = load_market_data_cached(conn)
        self.assertIs(load_market_data_cached(conn), m1)
        conn.execute("INSERT INTO price_history VALUES (1, '2024-01-02', 11.0, 'CAD')")
        cache.invalidate_on_price_update()
        m2 = load_market_data_cached(conn)
        self.assertIsNot(m2, m1)
        self.assertEqual(m2[0][(1, "2024-01-02")], 11.0)
        conn.close()


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
