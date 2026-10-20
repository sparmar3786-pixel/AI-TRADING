"""Regression tests for Level-2 modules; no live broker or Telegram calls."""
import unittest
from datetime import date
import pandas as pd

from quant.level2.backtest import BacktestConfig, run_backtest
from quant.level2.option_chain import AngelSymbolMaster
from quant.level2.websocket_angel import AngelWebSocketSupervisor
from quant.level2.ml_optimizer import MLFilter
from quant.level2.alerts import TelegramAlerts


class Level2Tests(unittest.TestCase):
    def test_symbol_master_resolves_expiry_ce_pe_and_strike_units(self):
        master = AngelSymbolMaster(cache_path="/tmp/not-used-level2.json")
        master._frame = pd.DataFrame([
            {"exch_seg": "NFO", "name": "NIFTY", "expiry": "29OCT2026", "strike": "2600000", "instrumenttype": "OPTIDX", "symbol": "NIFTY29OCT2626000CE", "token": "123", "lotsize": "65", "tick_size": "0.05"},
            {"exch_seg": "NFO", "name": "NIFTY", "expiry": "29OCT2026", "strike": "2600000", "instrumenttype": "OPTIDX", "symbol": "NIFTY29OCT2626000PE", "token": "124", "lotsize": "65", "tick_size": "0.05"},
        ])
        expiry = date(2026, 10, 29)
        contract = master.resolve("NFO", "NIFTY", expiry, 26000, "CE")
        self.assertIsNotNone(contract)
        self.assertEqual(contract.token, "123")
        self.assertEqual(contract.lot_size, 65)
        self.assertEqual(master.nearest_expiry("NFO", "NIFTY", date(2026, 10, 20)), expiry)
        self.assertEqual(master.atm_strike(26024, 50), 26000)

    def test_backtest_uses_prior_bars_and_stop_wins_when_both_touched(self):
        candles = pd.DataFrame([
            {"open": 100, "high": 101, "low": 99, "close": 100},
            {"open": 100, "high": 103, "low": 99, "close": 102},
            {"open": 102, "high": 111, "low": 94, "close": 105},
        ])
        seen_lengths = []
        def signal_fn(history, index):
            seen_lengths.append(len(history))
            return {"side": 1, "stop": 95, "target": 110} if index == 1 else None
        result = run_backtest(candles, signal_fn, BacktestConfig(initial_capital=10000, risk_fraction=0.01, slippage_bps=0))
        self.assertEqual(seen_lengths, [1, 2])
        self.assertEqual(result.trades[0]["reason"], "STOP")
        self.assertLess(result.trades[0]["pnl"], 0)

    def test_websocket_tick_parser_and_freshness_fail_closed(self):
        sup = AngelWebSocketSupervisor(lambda *_: None, lambda msg: msg)
        sup._on_message(("NIFTY", 100.0))
        self.assertIsNotNone(sup.latest("NIFTY"))
        self.assertIsNone(sup.latest("MISSING"))
        sup.stop()

    def test_ml_filter_does_not_approve_without_trained_model(self):
        filt = MLFilter()
        candles = pd.DataFrame({"close": [100 + i for i in range(40)], "high": [101 + i for i in range(40)], "low": [99 + i for i in range(40)]})
        self.assertFalse(filt.allow_trade(candles, 1))
        self.assertFalse(filt.allow_trade(candles, -1))

    def test_telegram_is_disabled_without_secrets(self):
        self.assertFalse(TelegramAlerts(token="", chat_id="").send("test"))


if __name__ == "__main__":
    unittest.main()
