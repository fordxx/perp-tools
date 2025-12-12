import unittest

from src.perpbot.models.position_snapshot import UnifiedPosition
from src.perpbot.positions.position_aggregator import PositionAggregator


class TestPositionAggregator(unittest.TestCase):
    def setUp(self):
        """Set up a common PositionAggregator instance for tests."""
        self.aggregator = PositionAggregator()

        # Mock positions for Binance
        self.pos_binance_btc = UnifiedPosition(
            "binance", "BTC-PERP", "LONG", 0.5, 35000, 70000, 71000, 500
        )
        self.pos_binance_eth = UnifiedPosition(
            "binance", "ETH-PERP", "LONG", 10, 35000, 3500, 3600, 1000
        )

        # Mock positions for Paradex
        self.pos_paradex_eth = UnifiedPosition(
            "paradex", "ETH-PERP", "SHORT", 5, 17500, 3500, 3400, 500
        )
        self.pos_paradex_sol = UnifiedPosition(
            "paradex", "SOL-PERP", "LONG", 100, 15000, 150, 155, 500
        )

        self.aggregator.update_positions_for_exchange(
            "binance", [self.pos_binance_btc, self.pos_binance_eth]
        )
        self.aggregator.update_positions_for_exchange(
            "paradex", [self.pos_paradex_eth, self.pos_paradex_sol]
        )

    def test_get_all_positions(self):
        """Test if it returns a flattened list of all positions."""
        all_positions = self.aggregator.get_all_positions()
        self.assertEqual(len(all_positions), 4)
        self.assertIn(self.pos_binance_btc, all_positions)
        self.assertIn(self.pos_paradex_sol, all_positions)

    def test_update_replaces_positions(self):
        """Test if updating an exchange replaces its old position list."""
        new_pos = UnifiedPosition("binance", "ADA-PERP", "LONG", 1000, 450, 0.45, 0.46, 10)
        self.aggregator.update_positions_for_exchange("binance", [new_pos])

        all_positions = self.aggregator.get_all_positions()
        self.assertEqual(len(all_positions), 3)  # 1 new from binance + 2 from paradex
        self.assertIn(new_pos, all_positions)
        self.assertNotIn(self.pos_binance_btc, all_positions)

    def test_get_net_exposure(self):
        """Test net exposure calculation (longs are positive, shorts are negative)."""
        # (35000 + 35000) - 17500 + 15000 = 67500
        expected_net_exposure = (
            self.pos_binance_btc.notional
            + self.pos_binance_eth.notional
            - self.pos_paradex_eth.notional
            + self.pos_paradex_sol.notional
        )
        self.assertAlmostEqual(self.aggregator.get_net_exposure(), expected_net_exposure)

    def test_get_gross_exposure(self):
        """Test gross exposure calculation (sum of absolute notional values)."""
        # 35000 + 35000 + 17500 + 15000 = 102500
        expected_gross_exposure = (
            self.pos_binance_btc.notional
            + self.pos_binance_eth.notional
            + self.pos_paradex_eth.notional
            + self.pos_paradex_sol.notional
        )
        self.assertAlmostEqual(self.aggregator.get_gross_exposure(), expected_gross_exposure)

    def test_get_exposure_by_symbol(self):
        """Test per-symbol net exposure calculation."""
        exposure = self.aggregator.get_exposure_by_symbol()
        self.assertAlmostEqual(exposure["BTC-PERP"], 35000)
        self.assertAlmostEqual(exposure["ETH-PERP"], 35000 - 17500)  # 17500
        self.assertAlmostEqual(exposure["SOL-PERP"], 15000)
        self.assertEqual(len(exposure), 3)