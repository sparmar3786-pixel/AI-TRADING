import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app

SMC_ENDPOINT = next(route.endpoint for route in app.routes if getattr(route, "path", None) == "/v1/smc/analyze")


class SmcApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_smc_endpoint_accepts_profile_tolerance_and_defaults_to_real_killzone(self):
        killzone = {
            "active": False,
            "window": None,
            "timezone": "America/New_York",
            "local_time": "2026-10-13T14:00:00-04:00",
        }
        with patch.dict(SMC_ENDPOINT.__globals__, {"ict_killzone_status": lambda: killzone}):
            response = self.client.post("/v1/smc/analyze", json={
                "instrument": "NIFTY",
                "strategy_format": "Guardeer",
                "htf_candles": [],
                "mtf_candles": [],
                "ltf_candles": [],
                "liquidity_tolerance": 1.25,
            })
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["strategy_format"], "Guardeer")
        self.assertEqual(body["liquidity_tolerance"], 1.25)
        self.assertFalse(body["in_killzone"])
        self.assertFalse(body["killzone_status"]["effective_active"])
        self.assertFalse(body["execution_allowed"])

    def test_smc_endpoint_accepts_inner_circle_without_manual_killzone_override(self):
        killzone = {
            "active": True,
            "window": "NEW_YORK_AM",
            "timezone": "America/New_York",
            "local_time": "2026-10-13T08:00:00-04:00",
        }
        with patch.dict(SMC_ENDPOINT.__globals__, {"ict_killzone_status": lambda: killzone}):
            response = self.client.post("/v1/smc/analyze", json={
                "instrument": "BANKNIFTY",
                "strategy_format": "Inner Circle",
                "htf_candles": [],
                "mtf_candles": [],
                "ltf_candles": [],
            })
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["strategy_format"], "Inner Circle")
        self.assertTrue(body["in_killzone"])
        self.assertEqual(body["killzone_status"]["window"], "NEW_YORK_AM")
        self.assertFalse(body["execution_allowed"])


if __name__ == "__main__":
    unittest.main()
