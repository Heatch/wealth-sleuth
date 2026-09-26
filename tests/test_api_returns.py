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


if __name__ == "__main__":
    unittest.main()
