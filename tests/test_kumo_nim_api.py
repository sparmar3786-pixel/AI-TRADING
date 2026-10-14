import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from backend.app import kumo_nim_api


class KumoNimApiTests(unittest.TestCase):
    def test_status_is_not_configured_without_base_url(self):
        with patch.dict(os.environ, {}, clear=True):
            result = kumo_nim_api.kumo_status("A" * 43)
        self.assertEqual(result["status"], "not_configured")
        self.assertFalse(result["ready"])
        self.assertFalse(result["general_chat_supported"])

    def test_predict_fails_closed_when_not_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as caught:
                kumo_nim_api.kumo_predict(
                    kumo_nim_api.KumoPredictionRequest(data=[{"rsi_14": 52.0}]),
                    "A" * 43,
                )
        self.assertEqual(caught.exception.status_code, 503)

    def test_predict_forwards_rows_and_marks_signal_only(self):
        with patch.dict(os.environ, {"KUMO_NIM_BASE_URL": "https://nim.example"}):
            with patch.object(kumo_nim_api, "_call_nim", return_value=(200, {"predictions": [{"label": "UP"}]}, 12.5)) as mocked:
                result = kumo_nim_api.kumo_predict(
                    kumo_nim_api.KumoPredictionRequest(data=[{"rsi_14": 52.0}], model="trading-model"),
                    "A" * 43,
                )
        mocked.assert_called_once_with("/v1/predictions", {"data": [{"rsi_14": 52.0}], "model": "trading-model"})
        self.assertEqual(result["provider"], "nvidia_kumo_tabular")
        self.assertTrue(result["signal_only"])
        self.assertFalse(result["order_placement_enabled"])


if __name__ == "__main__":
    unittest.main()
