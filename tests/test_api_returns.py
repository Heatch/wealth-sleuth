"""Smoke tests for the return-related API endpoints."""

import unittest

from fastapi.testclient import TestClient

from api.main import app


class ApiReturnTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_summary_returns_schema(self):
        res = self.client.get("/api/portfolio/summary?currency=CAD")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("returns", data)
        for key in ("m1", "m6", "ytd", "y1", "y3", "all"):
            with self.subTest(period=key):
                self.assertIn(key, data["returns"])
                self.assertIn("twr", data["returns"][key])
                self.assertIn("xirr", data["returns"][key])
                self.assertNotIn("mwr", data["returns"][key])
                self.assertNotIn("naive", data["returns"][key])

    def test_history_returns_schema(self):
        res = self.client.get("/api/portfolio/history?period=1y&currency=CAD")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("series", data)
        if data["series"]:
            pt = data["series"][0]
            self.assertIn("return_xirr", pt)
            self.assertIn("return_twr", pt)
            self.assertNotIn("return_pct", pt)

    def test_summary_with_account_filter(self):
        accounts = self.client.get("/api/accounts").json()["accounts"]
        if not accounts:
            self.skipTest("No accounts")
        ids = ",".join(str(a["id"]) for a in accounts if a["brokerage"].lower() == "disnat")
        if not ids:
            self.skipTest("No Disnat accounts")
        res = self.client.get(f"/api/portfolio/summary?currency=CAD&accounts={ids}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("returns", data)
        self.assertIn("xirr", data["returns"]["all"])
        self.assertIn("twr", data["returns"]["all"])

    def test_holdings_schema(self):
        res = self.client.get("/api/holdings?currency=CAD")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("holdings", data)
        if data["holdings"]:
            h = data["holdings"][0]
            self.assertIn("country", h)
            self.assertIn("sector", h)
            self.assertIn("industry", h)

    def test_symbol_filter_matches_holdings_value(self):
        """Allocation slice filtering must value only the selected securities."""
        holdings = self.client.get("/api/holdings?currency=CAD").json()["holdings"]
        if not holdings:
            self.skipTest("No holdings")
        # Pick the most common country to get a multi-symbol slice.
        countries: dict[str, float] = {}
        for h in holdings:
            c = h.get("country") or "Unknown"
            countries[c] = countries.get(c, 0.0) + (h["current_value"] or 0.0)
        target_country = max(countries, key=countries.get)
        slice_holdings = [h for h in holdings if (h.get("country") or "Unknown") == target_country]
        symbols = list(set(h["symbol"] for h in slice_holdings))
        expected_value = sum(h["current_value"] or 0.0 for h in slice_holdings)

        url = f"/api/portfolio/summary?currency=CAD&symbols={','.join(symbols)}"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertAlmostEqual(data["total_value"], expected_value, places=4)
        # Segment returns are now computed from the slice's transaction flows
        # and should be finite, reasonable numbers.
        for key in ("m1", "m6", "ytd", "y1", "y3", "all"):
            with self.subTest(period=key):
                self.assertIn("twr", data["returns"][key])
                self.assertIn("xirr", data["returns"][key])
        self.assertIsNone(data["cash_total"])

        hist = self.client.get(f"/api/portfolio/history?period=all&currency=CAD&symbols={','.join(symbols)}").json()
        self.assertTrue(len(hist["series"]) > 0)
        self.assertAlmostEqual(hist["series"][-1]["value"], expected_value, places=4)
        last_pt = hist["series"][-1]
        self.assertIsNotNone(last_pt.get("return_xirr"))
        self.assertIsNotNone(last_pt.get("return_twr"))
        # Later contributions must not be reported as performance. The naive
        # (end - start) / start figure is the +14,000% bug.
        priced = [p for p in hist["series"] if abs(p["value"]) > 1.0]
        self.assertGreaterEqual(len(priced), 2)
        naive = (priced[-1]["value"] - priced[0]["value"]) / abs(priced[0]["value"])
        twr = data["returns"]["all"]["twr"]
        self.assertIsNotNone(twr)
        self.assertAlmostEqual(last_pt["return_twr"], twr, places=6)
        if naive > 1.0:
            self.assertLess(abs(twr), naive / 5.0)
        self.assertGreater(twr, -0.95)
        self.assertLess(twr, 5.0)
        xirr = data["returns"]["all"]["xirr"]
        if xirr is not None:
            self.assertGreater(xirr, -0.95)
            self.assertLess(xirr, 5.0)

    def test_disnat_deposits_step_over_time(self):
        """Blank Disnat trade dates must not collapse every contribution onto day one."""
        accounts = self.client.get("/api/accounts").json()["accounts"]
        ids = [a["id"] for a in accounts if a["brokerage"].lower() == "disnat"]
        if not ids:
            self.skipTest("No Disnat accounts")
        res = self.client.get(
            "/api/portfolio/history?period=all&currency=CAD&accounts=" + ",".join(str(i) for i in ids)
        )
        self.assertEqual(res.status_code, 200)
        series = res.json()["series"]
        deps = [p["net_deposits"] for p in series if p.get("net_deposits") is not None]
        self.assertGreater(len(deps), 10)
        self.assertGreater(len({round(d, 2) for d in deps}), 1)
        self.assertLess(deps[0], deps[-1] - 100)

    def test_unfiltered_returns_stay_bounded(self):
        """Dietz blow-ups and double-counted opening deposits must not resurface."""
        res = self.client.get("/api/portfolio/summary?currency=CAD")
        self.assertEqual(res.status_code, 200)
        returns = res.json()["returns"]
        self.assertGreater(returns["all"]["twr"], -0.95)
        self.assertLess(returns["all"]["twr"], 5.0)
        self.assertGreater(returns["m1"]["xirr"], -0.5)
        self.assertLess(returns["m1"]["xirr"], 2.0)
        hist = self.client.get("/api/portfolio/history?period=1y&currency=CAD").json()
        self.assertAlmostEqual(
            hist["series"][-1]["return_twr"], returns["y1"]["twr"], places=6
        )

    def test_stacked_account_and_symbol_filters(self):
        """Brokerage/account filters and symbol filters can be combined."""
        holdings = self.client.get("/api/holdings?currency=CAD").json()["holdings"]
        accounts = self.client.get("/api/accounts").json()["accounts"]
        if not holdings or not accounts:
            self.skipTest("No data")

        # Pick a country slice and a Disnat account subset.
        countries = {}
        for h in holdings:
            c = h.get("country") or "Unknown"
            countries[c] = countries.get(c, 0.0) + (h["current_value"] or 0.0)
        country = max(countries, key=countries.get)
        country_symbols = list({h["symbol"] for h in holdings if (h.get("country") or "Unknown") == country})

        disnat_ids = [a["id"] for a in accounts if a["brokerage"].lower() == "disnat"]
        if not disnat_ids:
            self.skipTest("No Disnat accounts")

        params = {
            "currency": "CAD",
            "accounts": ",".join(str(i) for i in disnat_ids),
            "symbols": ",".join(country_symbols),
        }
        summary = self.client.get("/api/portfolio/summary", params=params).json()
        self.assertEqual(summary["currency"], "CAD")
        self.assertIn("returns", summary)

        hist = self.client.get("/api/portfolio/history?period=all&currency=CAD&accounts={}&symbols={}".format(
            ",".join(str(i) for i in disnat_ids),
            ",".join(country_symbols),
        )).json()
        self.assertTrue(len(hist["series"]) > 0)
        # Schema is present even when the overlap is empty.
        self.assertIn("return_twr", hist["series"][-1])
        self.assertIn("return_xirr", hist["series"][-1])

    def test_multiple_symbols_value_matches_holdings(self):
        """Selecting several securities at once values only those securities."""
        holdings = self.client.get("/api/holdings?currency=CAD").json()["holdings"]
        if len(holdings) < 2:
            self.skipTest("Need at least two holdings")
        symbols = [holdings[0]["symbol"], holdings[1]["symbol"]]
        expected = sum(h["current_value"] or 0.0 for h in holdings if h["symbol"] in symbols)
        summary = self.client.get(f"/api/portfolio/summary?currency=CAD&symbols={','.join(symbols)}").json()
        self.assertAlmostEqual(summary["total_value"], expected, places=4)

    def test_benchmarks_list(self):
        """Benchmark endpoint returns the three configured indices."""
        res = self.client.get("/api/benchmarks")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("benchmarks", data)
        symbols = {b["symbol"] for b in data["benchmarks"]}
        self.assertTrue(symbols.issuperset({"SPY", "XIU.TO", "QQQ"}))

    def test_benchmark_history_schema(self):
        """Benchmark history returns simulated series and returns."""
        res = self.client.get("/api/benchmarks/history?benchmarks=SPY&period=all&currency=CAD")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("benchmarks", data)
        self.assertIn("SPY", data["benchmarks"])
        spy = data["benchmarks"]["SPY"]
        self.assertIn("series", spy)
        self.assertIn("returns", spy)
        if spy["series"]:
            pt = spy["series"][0]
            self.assertIn("return_twr", pt)
            self.assertIn("return_xirr", pt)
            self.assertAlmostEqual(pt["return_twr"], 0.0, places=6)

    def test_benchmark_matches_portfolio_period_start(self):
        """Each benchmark starts at the portfolio value for that period."""
        for period in ("1m", "1y", "all"):
            with self.subTest(period=period):
                hist = self.client.get(f"/api/portfolio/history?period={period}&currency=CAD")
                bench = self.client.get(
                    f"/api/benchmarks/history?benchmarks=SPY,XIU.TO,QQQ&period={period}&currency=CAD"
                )
                self.assertEqual(hist.status_code, 200, hist.text)
                self.assertEqual(bench.status_code, 200, bench.text)
                portfolio = hist.json()["series"]
                if len(portfolio) < 2:
                    self.skipTest(f"No portfolio series for {period}")
                for symbol, data in bench.json()["benchmarks"].items():
                    series = data["series"]
                    self.assertGreaterEqual(len(series), 2, symbol)
                    self.assertEqual(series[0]["date"], portfolio[0]["date"], symbol)
                    self.assertAlmostEqual(series[0]["value"], portfolio[0]["value"], places=2)
                    self.assertAlmostEqual(series[0]["return_twr"], 0.0, places=6)
                    self.assertIsNotNone(series[-1]["return_twr"])
                    self.assertIsNotNone(series[-1]["return_xirr"])

    def test_benchmark_year_matches_portfolio_year_start(self):
        hist = self.client.get("/api/portfolio/history?period=all&currency=CAD&year=2024")
        bench = self.client.get(
            "/api/benchmarks/history?benchmarks=SPY&period=all&currency=CAD&year=2024"
        )
        self.assertEqual(hist.status_code, 200)
        self.assertEqual(bench.status_code, 200)
        portfolio = hist.json()["series"]
        spy = bench.json()["benchmarks"]["SPY"]["series"]
        self.assertTrue(spy)
        self.assertEqual(spy[0]["date"], portfolio[0]["date"])
        self.assertAlmostEqual(spy[0]["value"], portfolio[0]["value"], places=2)
        self.assertTrue(all(p["date"].startswith("2024-") for p in spy))
        self.assertAlmostEqual(spy[0]["return_twr"], 0.0, places=6)
        # Deposits during the year must not be booked as index performance.
        twr = spy[-1]["return_twr"]
        self.assertIsNotNone(twr)
        self.assertGreater(twr, -0.5)
        self.assertLess(twr, 1.0)
        naive = (spy[-1]["value"] - spy[0]["value"]) / abs(spy[0]["value"])
        self.assertNotAlmostEqual(twr, naive, places=2)

    def test_portfolio_history_year_filter(self):
        """Year parameter restricts history to a single calendar year."""
        res = self.client.get("/api/portfolio/history?period=all&currency=CAD&year=2024")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(len(data["series"]) > 0)
        self.assertTrue(all(p["date"].startswith("2024-") for p in data["series"]))

    def test_portfolio_summary_year_filter(self):
        """Year parameter snapshots summary at the end of the chosen year."""
        res = self.client.get("/api/portfolio/summary?currency=CAD&year=2024")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["as_of_date"].startswith("2024-"))
        self.assertIn("all", data["returns"])
        self.assertIsNotNone(data["returns"]["all"]["twr"])

    def _disnat_usd_accounts(self):
        accounts = self.client.get("/api/accounts").json()["accounts"]
        return [
            a
            for a in accounts
            if a["brokerage"].lower() == "disnat" and a["currency"] == "USD"
        ]

    def test_disnat_usd_xirr_bounded(self):
        """Security transfers into a USD sub-account are real cash flows.

        A TFSA USD account that receives DLR transfers (Nobert's Gambit) must
        not show a nonsensical all-time XIRR (e.g. +2034%) from treating those
        transfers as investment gain instead of deposits.
        """
        accounts = self._disnat_usd_accounts()
        if not accounts:
            self.skipTest("No Disnat USD accounts")
        for a in accounts:
            with self.subTest(account_id=a["id"], type=a["account_type"]):
                res = self.client.get(
                    f"/api/portfolio/summary?currency=CAD&accounts={a['id']}"
                )
                self.assertEqual(res.status_code, 200)
                xirr = res.json()["returns"]["all"]["xirr"]
                self.assertIsNotNone(xirr)
                self.assertGreater(xirr, -1.0)
                self.assertLess(xirr, 5.0)

    def test_disnat_usd_benchmark_tracks_portfolio(self):
        """A USD account's benchmark must stay in the portfolio's magnitude.

        Before the fix, the S&P 500 benchmark for a USD non-reg account could
        sit near $36 while the portfolio was worth hundreds, because a DLR
        transfer-in was not reinvested into the index.
        """
        accounts = self._disnat_usd_accounts()
        if not accounts:
            self.skipTest("No Disnat USD accounts")
        for a in accounts:
            with self.subTest(account_id=a["id"], type=a["account_type"]):
                hist = self.client.get(
                    f"/api/portfolio/history?period=all&currency=CAD&accounts={a['id']}"
                )
                bench = self.client.get(
                    f"/api/benchmarks/history?benchmarks=SPY&period=all&currency=CAD&accounts={a['id']}"
                )
                self.assertEqual(hist.status_code, 200)
                self.assertEqual(bench.status_code, 200)
                portfolio = hist.json()["series"]
                spy = bench.json()["benchmarks"]["SPY"]["series"]
                if len(portfolio) < 2 or len(spy) < 2:
                    continue
                # Start values must match exactly.
                self.assertEqual(spy[0]["date"], portfolio[0]["date"])
                self.assertAlmostEqual(spy[0]["value"], portfolio[0]["value"], places=2)
                # The benchmark must track the same order of magnitude, not be
                # ~10x smaller from a missed transfer-in.
                max_pv = max(p["value"] for p in portfolio)
                max_spy = max(p["value"] for p in spy)
                self.assertGreater(max_pv, 0.0)
                self.assertLess(abs(max_spy - max_pv) / max_pv, 10.0)

    def test_spinoff_holding_visible(self):
        """Spinoff receipts (e.g. SOBO) must appear in holdings, not just records.

        The holdings table is materialized; if it goes stale relative to the
        transactions (e.g. refreshed before spinoff handling existed), the
        position vanishes from holdings while records still show it.
        """
        res = self.client.get("/api/holdings?currency=CAD")
        self.assertEqual(res.status_code, 200)
        symbols = {h["symbol"] for h in res.json()["holdings"]}
        self.assertIn("SOBO", symbols)
        sobo = [h for h in res.json()["holdings"] if h["symbol"] == "SOBO"][0]
        self.assertGreater(sobo["quantity"], 0)
        self.assertIsNotNone(sobo["current_value"])

    def test_dividend_yields_sane(self):
        """Stored dividend yields must be decimal fractions, not percents.

        Yahoo sometimes reports yield as the percentage value itself
        (e.g. 0.99 for 0.99%); anything at/above 35% is a data error
        (e.g. Loblaws at 100%, Dollarama at 26%).
        """
        res = self.client.get("/api/holdings?currency=CAD")
        self.assertEqual(res.status_code, 200)
        for h in res.json()["holdings"]:
            y = h.get("dividend_yield")
            if y is not None:
                with self.subTest(symbol=h["symbol"]):
                    self.assertLess(y, 0.35)


if __name__ == "__main__":
    unittest.main()
