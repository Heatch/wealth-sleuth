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


if __name__ == "__main__":
    unittest.main()
