import os
import sys
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app

def patched_killzone(killzone):
    stack = ExitStack()
    for name, module in list(sys.modules.items()):
        if name.endswith("smc_api") and hasattr(module, "smc_analyze") and hasattr(module, "ict_killzone_status"):
            stack.enter_context(patch.object(module, "ict_killzone_status", return_value=killzone))
    return stack


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
        with patch.dict(os.environ, {
            "API_AUTH_MODE": "legacy",
            "API_ACCESS_KEY": "",
            "BACKEND_ACCESS_KEY": "",
            "FIREBASE_PROJECT_ID": "",
            "GOOGLE_CLOUD_PROJECT": "",
            "AUTH_ALLOWED_UIDS": "",
        }, clear=False):
            with patched_killzone(killzone):
                response = self.client.post("/v1/smc/analyze", headers={"X-Device-Id": "A" * 43}, json={
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



if __name__ == "__main__":
    unittest.main()
