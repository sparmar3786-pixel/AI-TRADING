import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from app import main as api


class BackendApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        self.device_headers = {"X-Device-Id": "A" * 43}

    def test_health_is_available_without_device_header(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_metadata_requires_valid_device_id_and_disables_orders(self):
        self.assertEqual(self.client.get("/v1/metadata").status_code, 401)
        response = self.client.get("/v1/metadata", headers=self.device_headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["signal_only"])
        self.assertFalse(response.json()["order_placement_enabled"])
        self.assertEqual(response.json()["minimum_confirmation_seconds"], 600)

    def test_connect_does_not_accept_missing_credentials_or_return_secrets(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(api, "_credential_path", return_value=Path(tmp) / "missing.enc"), \
             patch.object(api, "_adapter", None), \
             patch.dict(os.environ, {}, clear=True):
            response = self.client.post(
                "/v1/angel/connect",
                headers=self.device_headers,
                json={"remember_credentials": False},
            )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("ANGEL_API_KEY", response.text)

    def test_encryption_key_is_required_for_remembered_credentials(self):
        with patch.dict(os.environ, {"CREDENTIALS_ENCRYPTION_KEY": ""}, clear=False):
            with self.assertRaises(Exception):
                api._encryption_key()

    def test_encrypted_credential_store_never_persists_totp(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(api, "_credential_path", return_value=Path(tmp) / "angel.enc"), \
             patch.dict(os.environ, {"CREDENTIALS_ENCRYPTION_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}, clear=False):
            api._save_credentials({
                "angel_api_key": "example-key",
                "angel_client_code": "example-client",
                "angel_pin": "example-pin",
                "angel_totp_code": "654321",
            })
            stored = (Path(tmp) / "angel.enc").read_text()
            loaded = api._load_credentials()
        self.assertNotIn("654321", stored)
        self.assertNotIn("angel_totp", loaded)
        self.assertEqual(loaded["angel_client_code"], "example-client")

    def test_book_parser_does_not_invent_quotes_or_depth(self):
        self.assertEqual(api._book({}), (None, None, 0, 0))
        bid, ask, buy, sell = api._book({
            "best5Data": {
                "buy": [{"price": "100.0", "quantity": "7"}],
                "sell": [{"price": "100.5", "quantity": "4"}],
            }
        })
        self.assertEqual((bid, ask, buy, sell), (100.0, 100.5, 7.0, 4.0))

    def test_timestamp_parser_rejects_unknown_source_format(self):
        self.assertIsNone(api._iso("not-a-market-timestamp"))
        self.assertIsNotNone(api._iso("12-Oct-2026 10:00:00"))


if __name__ == "__main__":
    unittest.main()
