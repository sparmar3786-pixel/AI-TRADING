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
