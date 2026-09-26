"""Period-specific benchmark simulation."""

import unittest
from datetime import date, timedelta

from api.services.benchmarks import simulate_index_path
from api.services.returns import returns_for_range


def _dates(start: str, n: int) -> list[str]:
    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(n)]


class BenchmarkSimulationTests(unittest.TestCase):
    def test_starts_at_portfolio_value(self):
        window = [("2024-01-01", 1000.0), ("2024-01-02", 1010.0)]
        prices = {"2024-01-01": 100.0, "2024-01-02": 110.0}
        series, flows, daily = simulate_index_path(window, {}, lambda d: prices[d])
        self.assertEqual(series[0], ("2024-01-01", 1000.0))
        self.assertAlmostEqual(series[1][1], 1100.0, places=6)
        self.assertEqual(flows, {})
        self.assertAlmostEqual(daily["2024-01-02"], 0.10, places=6)

    def test_deposit_is_not_performance(self):
        """A mid-window deposit increases value but not that day's TWR."""
        window = [
            ("2024-01-01", 1000.0),
            ("2024-01-02", 1000.0),
            ("2024-06-01", 1000.0),
        ]
        prices = {d: 100.0 for d, _ in window}
        series, flows, daily = simulate_index_path(
            window, {"2024-01-02": 500.0}, lambda d: prices[d]
        )
        self.assertAlmostEqual(series[0][1], 1000.0, places=6)
        self.assertAlmostEqual(series[1][1], 1500.0, places=6)
        self.assertAlmostEqual(daily["2024-01-02"], 0.0, places=6)
        self.assertAlmostEqual(flows["2024-01-02"], 500.0, places=6)

        per, history = returns_for_range(
            series, flows, {}, 0.0, series[0][0], series[-1][0], daily_returns=daily
        )
        self.assertAlmostEqual(history[0]["return_twr"], 0.0, places=6)
        self.assertAlmostEqual(history[1]["return_twr"], 0.0, places=6)
        self.assertAlmostEqual(per["twr"], 0.0, places=6)
        # Naive (end - start) / start would be +50%. TWR must not be that.
        naive = (series[-1][1] - series[0][1]) / series[0][1]
        self.assertAlmostEqual(naive, 0.5, places=6)
        self.assertNotAlmostEqual(per["twr"], naive, places=4)
        self.assertIsNotNone(per["xirr"])
        self.assertAlmostEqual(per["xirr"], 0.0, places=4)

    def test_price_gain_with_no_flows_is_the_return(self):
        days = _dates("2024-01-01", 366)
        window = [(d, 1000.0) for d in days]
        # Price rises 10% over the year, linearly in the lookup.
        start_px, end_px = 100.0, 110.0

        def price_on(d: str) -> float:
            i = days.index(d)
            return start_px + (end_px - start_px) * i / (len(days) - 1)

        series, flows, daily = simulate_index_path(window, {}, price_on)
        self.assertEqual(flows, {})
        self.assertAlmostEqual(series[0][1], 1000.0, places=4)
        self.assertAlmostEqual(series[-1][1], 1100.0, places=4)
        per, history = returns_for_range(
            series, flows, {}, 0.0, series[0][0], series[-1][0], daily_returns=daily
        )
        self.assertAlmostEqual(history[0]["return_twr"], 0.0, places=6)
        self.assertAlmostEqual(per["twr"], 0.10, places=4)
        self.assertAlmostEqual(per["xirr"], 0.10, places=3)

    def test_opening_flow_is_not_applied_twice(self):
        window = [("2024-01-01", 1000.0), ("2024-01-02", 1000.0)]
        series, flows, _daily = simulate_index_path(
            window,
            {"2024-01-01": 1000.0, "2024-01-02": 0.0},
            lambda d: 50.0,
        )
        self.assertAlmostEqual(series[0][1], 1000.0, places=6)
        self.assertAlmostEqual(series[1][1], 1000.0, places=6)
        self.assertNotIn("2024-01-01", flows)

    def test_withdrawal_cannot_short_the_index(self):
        window = [("2024-01-01", 100.0), ("2024-01-02", 100.0)]
        series, flows, _daily = simulate_index_path(
            window, {"2024-01-02": -250.0}, lambda d: 10.0
        )
        self.assertAlmostEqual(series[1][1], 0.0, places=6)
        self.assertAlmostEqual(flows["2024-01-02"], -100.0, places=6)


if __name__ == "__main__":
    unittest.main()
