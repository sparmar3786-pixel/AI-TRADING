import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from backend.app import kumo_nim_api


DEVICE = "A" * 43
VALID_REQUEST = {
    "model": "kumo-tabular",
    "task": {"kind": "classification", "target": {"column_name": "direction", "dtype": "string", "classes": ["DOWN", "UP"]}},
    "schema": {"instance_table": {"columns": {"rsi_14": {"dtype": "float64", "stype": "numerical"}, "direction": {"dtype": "string", "stype": "categorical"}}, "primary_key": "id"}, "related_tables": {}, "relationships": []},
    "context": {"instance_table": {"format": "arrays", "columns": ["rsi_14", "direction"], "rows": [[42.0, "DOWN"], [61.0, "UP"]]}, "related_tables": {}},
    "predict": {"instance_table": {"format": "arrays", "columns": ["rsi_14"], "rows": [[55.0]]}, "related_tables": {}},
    "output": {"fields": ["prediction", "probabilities"]},
    "metadata": {"request_id": "test-kumo"},
}


class KumoNimApiTests(unittest.TestCase):
    def test_status_is_not_configured_without_any_provider(self):
        with patch.dict(os.environ, {}, clear=True):
            result = kumo_nim_api.kumo_status(DEVICE)
        self.assertEqual(result["status"], "not_configured")
        self.assertFalse(result["ready"])
        self.assertFalse(result["general_chat_supported"])

    def test_predict_fails_closed_when_not_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as caught:
                kumo_nim_api.kumo_predict(
                    kumo_nim_api.KumoPredictionRequest(request=VALID_REQUEST), DEVICE
                )
        self.assertEqual(caught.exception.status_code, 503)

    def test_hosted_status_checks_models_endpoint_with_bearer_key(self):
        with patch.dict(os.environ, {"KUMO_NVIDIA_API_KEY": "test-token"}, clear=True):
            with patch.object(kumo_nim_api, "_http_json", return_value=(200, {"data": ["kumo-tabular"]}, 8.2)) as mocked:
                result = kumo_nim_api.kumo_status(DEVICE)
        mocked.assert_called_once_with(kumo_nim_api.NVIDIA_CATALOG_BASE + "/models", token="test-token")
        self.assertEqual(result["mode"], "hosted_api_catalog")
        self.assertTrue(result["ready"])

    def test_hosted_prediction_forwards_full_envelope(self):
        with patch.dict(os.environ, {"KUMO_NVIDIA_API_KEY": "test-token"}, clear=True):
            with patch.object(kumo_nim_api, "_http_json", return_value=(200, {"predictions": [{"prediction": "UP"}]}, 12.5)) as mocked:
                result = kumo_nim_api.kumo_predict(
                    kumo_nim_api.KumoPredictionRequest(request=VALID_REQUEST), DEVICE
                )
        mocked.assert_called_once_with(
            kumo_nim_api.NVIDIA_CATALOG_BASE + "/predictions",
            method="POST",
            payload=VALID_REQUEST,
            token="test-token",
        )
        self.assertEqual(result["provider"], "nvidia_kumo_tabular")
        self.assertEqual(result["mode"], "hosted_api_catalog")
        self.assertTrue(result["signal_only"])
        self.assertFalse(result["order_placement_enabled"])

    def test_hosted_prediction_rejects_legacy_data_shape(self):
        with patch.dict(os.environ, {"KUMO_NVIDIA_API_KEY": "test-token"}, clear=True):
            with self.assertRaises(HTTPException) as caught:
                kumo_nim_api.kumo_predict(
                    kumo_nim_api.KumoPredictionRequest(data=[{"rsi_14": 52.0}]), DEVICE
                )
        self.assertEqual(caught.exception.status_code, 422)

    def test_self_hosted_prediction_forwards_full_envelope(self):
        with patch.dict(os.environ, {"KUMO_NIM_BASE_URL": "https://nim.example"}, clear=True):
            with patch.object(kumo_nim_api, "_self_hosted_call", return_value=(200, {"predictions": []}, 12.5)) as mocked:
                result = kumo_nim_api.kumo_predict(
                    kumo_nim_api.KumoPredictionRequest(request=VALID_REQUEST), DEVICE
                )
        mocked.assert_called_once_with("/v1/predictions", VALID_REQUEST)
        self.assertEqual(result["mode"], "self_hosted_nim")


if __name__ == "__main__":
    unittest.main()
