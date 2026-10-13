import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app import main as api


class StrategySuiteApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        self.headers = {"X-Device-Id": "A" * 43}

    def test_evaluate_strategy_suite_is_research_only(self):
        candles = [
            {"high": 101 + i, "low": 99 + i, "close": 100 + i, "volume": 1000}
            for i in range(35)
        ]
        response = self.client.post(
            "/v1/strategies/evaluate",
            headers=self.headers,
            json={"candles": candles, "oi_change": 120, "min_consensus": 3},
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["status"], "ok")
        self.assertIn("ema_9_21", result["strategies"])
        self.assertIn("oi_context", result)
        self.assertFalse(result["order_placement_enabled"])
        self.assertEqual(result["execution"], "disabled")
        trace = result["trace"]
        self.assertTrue(trace["execution_id"].startswith("strategy-"))
        self.assertEqual(trace["strategy_version"], "strategy-suite-v1")
        self.assertEqual(trace["input_candle_count"], len(candles))
        self.assertEqual(len(trace["input_sha256"]), 64)
        self.assertFalse(trace["ai_consumed"])
        self.assertFalse(trace["research_engine_received"])
        self.assertFalse(trace["trading_setup_received"])
        self.assertEqual(trace["downstream_status"], "NOT_CONNECTED")
        strategy_trace = result["strategy_trace"]
        self.assertEqual(len(strategy_trace), len(result["strategies"]))
        for item in strategy_trace:
            self.assertEqual(item["execution_id"], trace["execution_id"])
            self.assertEqual(item["strategy_version"], trace["strategy_version"])
            self.assertEqual(item["input_candle_count"], len(candles))
            self.assertEqual(item["input_sha256"], trace["input_sha256"])
            self.assertIn(item["signal"], ("LONG", "SHORT", "WAIT"))
            self.assertIsNone(item["score"])
            self.assertEqual(item["score_status"], "NOT_COMPUTED_BY_RULE")
            self.assertFalse(item["ai_consumed"])
            self.assertFalse(item["order_placement_enabled"])

    def test_evaluate_strategy_suite_rejects_empty_history(self):
        response = self.client.post(
            "/v1/strategies/evaluate",
            headers=self.headers,
            json={"candles": []},
        )
        self.assertEqual(response.status_code, 422)

    def test_evaluate_strategy_suite_requires_device_id(self):
        response = self.client.post(
            "/v1/strategies/evaluate",
            json={"candles": [{"high": 2, "low": 1, "close": 1.5}]},
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
