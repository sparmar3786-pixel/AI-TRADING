import unittest
from datetime import datetime, timezone
from strategies.smc import analyze_smc, analyze_guardeer, analyze_inner_circle, detect_fvg, detect_order_blocks, ict_killzone_status


def bars(values):
    return [{"open": o, "high": h, "low": l, "close": c} for o,h,l,c in values]


class SmcTests(unittest.TestCase):
    def test_fvg_detects_bullish_gap(self):
        candles = bars([(10,11,9,10),(10,11,9,10),(12,14,12,13)])
        self.assertEqual(detect_fvg(candles)[0]["type"], "bullish")

    def test_order_block_detects_bullish_displacement(self):
        candles = bars([(10,11,8,9),(9,13,9,12)])
        self.assertTrue(any(x["type"] == "bullish" for x in detect_order_blocks(candles)))

    def test_no_candles_never_generates_trade(self):
        result = analyze_smc([], [], [], instrument="CRUDEOIL")
        self.assertEqual(result["signal"], "NO TRADE")
        self.assertFalse(result["execution_allowed"])
        self.assertIn("Insufficient candles", " ".join(result["reasons"]))

    def test_index_and_mcx_instrument_labels_preserved(self):
        for symbol in ("NIFTY", "BANKNIFTY", "CRUDEOIL", "GOLDM"):
            self.assertEqual(analyze_smc([], [], [], instrument=symbol)["instrument"], symbol)

    def test_guardeer_profile_is_labeled_and_never_trades_without_candles(self):
        result = analyze_guardeer([], [], [])
        self.assertEqual(result['strategy_format'], 'Guardeer')
        self.assertIn('lecture_11_true_ict', result['format_modules'])
        self.assertEqual(result['signal'], 'NO TRADE')

    def test_inner_circle_profile_exposes_ict_core_modules(self):
        result = analyze_inner_circle([], [], [], in_killzone=False)
        self.assertEqual(result['strategy_format'], 'Inner Circle')
        self.assertIn('power_of_3', result['format_modules'])
        self.assertFalse(result['format_modules']['killzone_filter'])
        self.assertEqual(result['signal'], 'NO TRADE')

    def test_ict_killzones_use_dst_aware_new_york_time(self):
        london = ict_killzone_status(datetime(2026, 10, 13, 6, 30, tzinfo=timezone.utc))
        self.assertTrue(london["active"])
        self.assertEqual(london["window"], "LONDON")
        ny_am = ict_killzone_status(datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc))
        self.assertTrue(ny_am["active"])
        self.assertEqual(ny_am["window"], "NEW_YORK_AM")
        asia = ict_killzone_status(datetime(2026, 10, 14, 0, 30, tzinfo=timezone.utc))
        self.assertTrue(asia["active"])
        self.assertEqual(asia["window"], "ASIA")
        inactive = ict_killzone_status(datetime(2026, 10, 13, 18, 0, tzinfo=timezone.utc))
        self.assertFalse(inactive["active"])
        self.assertIsNone(inactive["window"])

    def test_strategy_profiles_accept_api_liquidity_tolerance(self):
        guardeer = analyze_guardeer([], [], [], liquidity_tolerance=1.25)
        inner_circle = analyze_inner_circle([], [], [], liquidity_tolerance=2.5)
        self.assertEqual(guardeer["liquidity_tolerance"], 1.25)
        self.assertEqual(inner_circle["liquidity_tolerance"], 2.5)

    def test_liquidity_tolerance_is_configurable(self):
        a = analyze_smc([], [], [], instrument="NIFTY", liquidity_tolerance=1.25)
        self.assertEqual(a["liquidity_tolerance"], 1.25)


if __name__ == "__main__":
    unittest.main()
