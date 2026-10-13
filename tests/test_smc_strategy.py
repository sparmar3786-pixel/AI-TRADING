import unittest
from strategies.smc import analyze_smc, detect_fvg, detect_order_blocks


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

    def test_liquidity_tolerance_is_configurable(self):
        a = analyze_smc([], [], [], instrument="NIFTY", liquidity_tolerance=1.25)
        self.assertEqual(a["liquidity_tolerance"], 1.25)


if __name__ == "__main__":
    unittest.main()
