import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from app import main as api
from app import kumo_nim_api


class KumoQuantBridgeTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        self.headers = {"X-Device-Id": "A" * 43}

    def test_real_kumo_inference_is_attached_to_quant_without_changing_decision(self):
        snapshot = {
            "signals": {
                "NIFTY": {
                    "decision": "WAIT",
                    "quant_engine": {"decision": "WAIT", "passed_layers": 2},
                    "live_validation": {"verdict": "WAIT", "blocks": ["STALE_MARKET_DATA"]},
                }
            },
            "market": {"NIFTY": {"ltp": 25000.0, "source": "angelone_smartapi"}},
        }
        envelope = {
            "model": "kumo-tabular",
            "task": {"type": "classification"},
            "schema": {"fields": []},
            "context": {"rows": []},
            "predict": {"rows": []},
            "output": {"fields": ["prediction", "probabilities"]},
        }
        prediction = {"predictions": [{"prediction": "UP", "probabilities": {"UP": 0.61, "DOWN": 0.39}}]}
        with patch.dict(os.environ, {"KUMO_NVIDIA_API_KEY": "kumo-test-key"}, clear=False), \\
             patch.object(kumo_nim_api, "_http_json", return_value=(200, prediction, 17.5)) as upstream, \\
             patch.object(api, "_get_signals", return_value=snapshot):
            response = self.client.post(
                "/v1/ai/kumo/predict",
                headers=self.headers,
                json={"request": envelope, "index": "NIFTY"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["quant_connection"]["connected"])
        self.assertEqual(body["quant_connection"]["quant_decision"], "WAIT")
        self.assertEqual(body["quant_connection"]["deterministic_gate_verdict"], "WAIT")
        self.assertFalse(body["quant_connection"]["decision_changed_by_kumo"])
        evidence = body["quant_connection"]["quant_engine"]["kumo_tabular_evidence"]
        self.assertEqual(evidence["status"], "inference_received")
        self.assertEqual(evidence["prediction"], prediction)
        self.assertFalse(evidence["prediction_used_as_trade_authority"])
        self.assertEqual(snapshot["signals"]["NIFTY"]["quant_engine"], {"decision": "WAIT", "passed_layers": 2})
        upstream.assert_called_once()

    def test_kumo_quant_bridge_rejects_unsupported_index(self):
        envelope = {
            "model": "kumo-tabular",
            "task": {}, "schema": {}, "context": {}, "predict": {},
            "output": {"fields": ["prediction"]},
        }
        with patch.dict(os.environ, {"KUMO_NVIDIA_API_KEY": "kumo-test-key"}, clear=False), \\
             patch.object(kumo_nim_api, "_http_json", return_value=(200, {"predictions": []}, 1.0)):
            response = self.client.post(
                "/v1/ai/kumo/predict",
                headers=self.headers,
                json={"request": envelope, "index": "NOT_AN_INDEX"},
            )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
