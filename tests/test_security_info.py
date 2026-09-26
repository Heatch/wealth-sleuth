"""Tests for security info enrichment rules."""

import unittest

from fetch_security_info import infer_etf_country, infer_etf_sector_industry, resolve_ticker


class TickerResolutionTests(unittest.TestCase):
    def test_plain_cad_symbol(self):
        """Undotted CAD symbols keep the classic .TO/.V/.CN order."""
        self.assertEqual(
            resolve_ticker("RY", "CAD", 0),
            ["RY.TO", "RY.V", "RY.CN", "RY"],
        )

    def test_dotted_cad_class_share_prefers_dash(self):
        """Yahoo lists class shares with a dash (HMM.A -> HMM-A.TO)."""
        cands = resolve_ticker("HMM.A", "CAD", 0)
        self.assertEqual(cands[0], "HMM-A.TO")
        self.assertIn("HMM.A.TO", cands)

    def test_dotted_usd_class_share(self):
        self.assertEqual(resolve_ticker("BRK.B", "USD", 0), ["BRK.B", "BRK-B"])


class ETFClassificationTests(unittest.TestCase):
    def test_gold_etf_basic_materials(self):
        info = {"longName": "SPDR Gold Shares", "exchange": "PCX"}
        sector, industry = infer_etf_sector_industry(info)
        self.assertEqual(sector, "Basic Materials")
        self.assertEqual(industry, "Precious Metals")

    def test_uranium_etf_basic_materials(self):
        info = {"longName": "VanEck Uranium and Nuclear ETF", "exchange": "PCX"}
        sector, industry = infer_etf_sector_industry(info)
        self.assertEqual(sector, "Basic Materials")
        self.assertEqual(industry, "Uranium")

    def test_tbill_etf_fixed_income(self):
        info = {"longName": "Global X 0-3 Month T-Bill ETF", "exchange": "TOR"}
        sector, industry = infer_etf_sector_industry(info)
        self.assertEqual(sector, "Fixed Income")

    def test_currency_etf(self):
        info = {"longName": "Global X U.S. Dollar Currency ETF", "exchange": "TOR"}
        sector, industry = infer_etf_sector_industry(info)
        self.assertEqual(sector, "Currency")

    def test_broad_equity_etf(self):
        info = {"longName": "BetaPro NASDAQ-100 2x Daily Bull ETF", "exchange": "TOR"}
        sector, industry = infer_etf_sector_industry(info)
        self.assertEqual(sector, "Equities")


class ETFCountryTests(unittest.TestCase):
    def test_global_x_not_international(self):
        """The fund family 'Global X' must not be treated as a global mandate."""
        info = {"longName": "Global X Gold ETF", "exchange": "TOR"}
        self.assertEqual(infer_etf_country(info), "Canada")

    def test_nasdaq_etf_usa(self):
        info = {"longName": "BetaPro NASDAQ-100 2x Daily Bull ETF", "exchange": "TOR"}
        self.assertEqual(infer_etf_country(info), "United States")

    def test_international_etf(self):
        info = {"longName": "iShares MSCI World Index ETF", "exchange": "TOR"}
        self.assertEqual(infer_etf_country(info), "International")

    def test_etf_exchange_fallback(self):
        info = {"longName": "SPDR Gold Shares", "exchange": "PCX"}
        self.assertEqual(infer_etf_country(info), "United States")


if __name__ == "__main__":
    unittest.main()
