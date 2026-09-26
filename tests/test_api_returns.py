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
        # Segment returns are intentionally hidden because the sub-portfolio
        # can drop to zero between trades.
        self.assertIsNone(data["returns"]["all"]["twr"])
        self.assertIsNone(data["returns"]["all"]["xirr"])
        self.assertIsNone(data["cash_total"])

        hist = self.client.get(f"/api/portfolio/history?period=all&currency=CAD&symbols={','.join(symbols)}").json()
        self.assertTrue(len(hist["series"]) > 0)
        self.assertAlmostEqual(hist["series"][-1]["value"], expected_value, places=4)


if __name__ == "__main__":
    unittest.main()
