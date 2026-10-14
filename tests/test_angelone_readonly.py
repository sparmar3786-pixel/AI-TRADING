import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from integrations.angelone_readonly import AngelOneConfigError, AngelOneReadOnly


class AngelOneReadOnlyTests(unittest.TestCase):
    def test_missing_credentials_fail_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AngelOneConfigError):
                AngelOneReadOnly().profile()

    def test_invalid_exchange_rejected_before_login(self):
        with self.assertRaises(ValueError):
            AngelOneReadOnly().ltp("CRYPTO", "X", "1")

    def test_empty_contract_rejected_before_login(self):
        with self.assertRaises(ValueError):
            AngelOneReadOnly().ltp("NSE", "", "1")

    def _mock_sdk(self):
        client = MagicMock()
        client.refresh_token = "refresh-token-only-in-test"
        client.generateSession.return_value = {
            "status": True,
            "data": {"clientcode": "demo-client", "name": "Test User"},
        }
        client.getProfile.return_value = {
            "status": True,
            "data": {"clientcode": "demo-client", "name": "Test User"},
        }
        client.ltpData.return_value = {
            "status": True,
            "data": {"ltp": 22100.5, "exchange_timestamp": "12-Oct-2026 10:00:00"},
        }
        client.getMarketData.return_value = {
            "status": True,
            "data": {"fetched": [{"symbolToken": "123", "ltp": 100.0}], "unfetched": []},
        }
        client.getCandleData.return_value = {
            "status": True,
            "data": [["2026-10-12T10:00:00+05:30", 100, 102, 99, 101, 5000]],
        }
        client.optionGreek.return_value = {
            "status": True,
            "data": [{"strikePrice": "22000", "optionType": "CE", "delta": "0.51"}],
        }
        smartapi = types.ModuleType("SmartApi")
        smartapi.SmartConnect = MagicMock(return_value=client)
        pyotp = types.ModuleType("pyotp")
        pyotp.TOTP = MagicMock(return_value=types.SimpleNamespace(now=lambda: "123456"))
        return client, {"SmartApi": smartapi, "pyotp": pyotp}

    def test_current_sdk_profile_response_can_use_token_from_sdk_state(self):
        client, modules = self._mock_sdk()
        env = {
            "ANGEL_API_KEY": "test-api-key",
            "ANGEL_CLIENT_CODE": "demo-client",
            "ANGEL_PIN": "test-pin",
            "ANGEL_TOTP_SECRET": "test-totp-secret",
        }
        with patch.dict(os.environ, env), patch.dict(sys.modules, modules):
            adapter = AngelOneReadOnly()
            result = adapter.profile()
        self.assertEqual(result["client_code"], "demo-client")
        self.assertNotIn("refresh-token-only-in-test", repr(result))
        client.generateSession.assert_called_once()

    def test_read_only_quote_candles_and_greeks(self):
        client, modules = self._mock_sdk()
        env = {
            "ANGEL_API_KEY": "test-api-key",
            "ANGEL_CLIENT_CODE": "demo-client",
            "ANGEL_PIN": "test-pin",
            "ANGEL_TOTP_SECRET": "test-totp-secret",
        }
        with patch.dict(os.environ, env), patch.dict(sys.modules, modules):
            adapter = AngelOneReadOnly()
            quote = adapter.market_data("FULL", {"NFO": ["123"]})
            candles = adapter.candles("NSE", "99926000", "FIVE_MINUTE", "2026-10-12 09:15", "2026-10-12 10:00")
            greeks = adapter.option_greeks("NIFTY", "29OCT2026")
        self.assertEqual(quote["data"]["fetched"][0]["ltp"], 100.0)
        self.assertEqual(len(candles["candles"]), 1)
        self.assertEqual(greeks["data"][0]["delta"], "0.51")
        client.getMarketData.assert_called_once_with("FULL", {"NFO": ["123"]})
        client.getCandleData.assert_called_once()
        client.optionGreek.assert_called_once_with({"name": "NIFTY", "expirydate": "29OCT2026"})

    def test_invalid_candle_range_rejected_before_login(self):
        with self.assertRaises(ValueError):
            AngelOneReadOnly().candles("NSE", "99926000", "FIVE_MINUTE", "2026-10-12 10:00", "2026-10-12 09:00")

    def test_market_quote_limits_rejected_before_login(self):
        with self.assertRaises(ValueError):
            AngelOneReadOnly().market_data("FULL", {"NFO": [str(i) for i in range(51)]})


    def test_six_digit_current_totp_is_passed_directly_to_smartapi(self):
        client, modules = self._mock_sdk()
        # A six-digit OTP is a generated code, not a Base32 TOTP secret.
        modules["pyotp"].TOTP.side_effect = ValueError("Non-base32 digit found")
        credentials = {
            "angel_api_key": "test-api-key",
            "angel_client_code": "demo-client",
            "angel_pin": "test-pin",
            "angel_totp_secret": "123456",
        }
        with patch.dict(os.environ, {}, clear=True), patch.dict(sys.modules, modules):
            adapter = AngelOneReadOnly(credentials)
            result = adapter.profile()
        self.assertEqual(result["client_code"], "demo-client")
        client.generateSession.assert_called_once_with("demo-client", "test-pin", "123456")


if __name__ == "__main__":
    unittest.main()
