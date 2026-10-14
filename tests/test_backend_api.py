import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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

    def test_provider_json_retries_one_transient_503(self):
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self):
                return json.dumps({"choices": [{"message": {"content": "ROUTER_OK"}}]}).encode()

        transient = api.urllib.error.HTTPError(
            "https://openrouter.ai/api/v1/chat/completions", 503, "Service Unavailable", {}, None
        )
        request = api.urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=b"{}", headers={"Content-Type": "application/json"}, method="POST",
        )
        with patch.object(api.urllib.request, "urlopen", side_effect=[transient, FakeResponse()]) as urlopen:
            result = api._provider_json_with_retry(request, timeout=1, provider="openrouter")
        self.assertEqual(result["choices"][0]["message"]["content"], "ROUTER_OK")
        self.assertEqual(urlopen.call_count, 2)

    def test_credentials_from_env_accepts_railway_angel_client_id_name(self):
        keys = ("ANGEL_API_KEY", "ANGEL_CLIENT_CODE", "ANGEL_CLIENT_ID", "ANGEL_PIN", "ANGEL_TOTP_SECRET")
        with patch.dict(os.environ, {
            "ANGEL_API_KEY": "api-test",
            "ANGEL_CLIENT_ID": "client-test",
            "ANGEL_PIN": "pin-test",
            "ANGEL_TOTP_SECRET": "totp-test",
        }, clear=False):
            os.environ.pop("ANGEL_CLIENT_CODE", None)
            credentials = api._credentials_from_env()
        self.assertEqual(credentials["angel_client_code"], "client-test")
        self.assertEqual(set(credentials), {"angel_api_key", "angel_client_code", "angel_pin", "angel_totp_secret"})

    def test_live_validation_contract_returns_explicit_checks_and_fails_closed(self):
        result = {"decision": "CALL BUY", "entry": 100.0, "stop_loss": 90.0, "target": 120.0}
        layers = {
            "data_quality": {"pass": True, "age_seconds": 3.0},
            "trend_sentiment": {"pass": True, "trend": "BULLISH"},
            "order_flow": {"pass": True},
            "option_selection": {"pass": True},
            "risk_levels": {"pass": True, "reward_risk": 2.0},
            "confirmation": {"pass": True},
        }
        passed = api._live_validation_contract(result, layers, 2.0)
        self.assertEqual(passed["verdict"], "PASS")
        self.assertTrue(passed["checks"]["fresh_market_data"])
        self.assertTrue(passed["checks"]["valid_option_quote"])
        self.assertEqual(passed["decision"], "CALL BUY")

        stale_quote = api._live_validation_contract(result, layers, 90.0)
        self.assertEqual(stale_quote["verdict"], "WAIT")
        self.assertEqual(stale_quote["decision"], "WAIT")
        self.assertFalse(stale_quote["checks"]["valid_option_quote"])

        bad_levels = api._live_validation_contract({**result, "stop_loss": 105.0}, layers, 2.0)
        self.assertEqual(bad_levels["verdict"], "WAIT")
        self.assertFalse(bad_levels["checks"]["valid_sl_target"])

        conflicting_ai = api._live_validation_contract(result, layers, 2.0, {"ok": True, "decision": "PUT BUY"})
        self.assertEqual(conflicting_ai["verdict"], "WAIT")
        self.assertFalse(conflicting_ai["checks"]["ai_direction_consistent"])
    def test_wait_signal_always_returns_fail_closed_validation_checks(self):
        signal = api._wait_signal("NIFTY", "No fresh quote")
        self.assertEqual(signal["decision"], "WAIT")
        self.assertEqual(signal["live_validation"]["verdict"], "WAIT")
        self.assertIn("checks", signal["live_validation"])
        self.assertFalse(any(signal["live_validation"]["checks"].values()))
    def test_nvidia_review_cannot_override_or_conflict_with_deterministic_candidate(self):
        payload = {
            "market": {"NIFTY": {"ltp": 25000.0, "age_seconds": 3.0, "live": True}},
            "signals": {"NIFTY": {
                "decision": "CALL BUY", "entry": 100.0, "stop_loss": 90.0, "target": 120.0,
                "live_validation": {"verdict": "PASS", "checks": {
                    "fresh_market_data": True, "valid_option_quote": True, "five_layer_engine": True,
                    "valid_sl_target": True, "risk_checks": True, "ai_direction_consistent": True,
                }, "blocks": []},
            }},
        }
        with (
            patch.object(api, "_signal_cache", payload),
            patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key", "KUMO_NVIDIA_API_KEY": ""}, clear=False),
            patch.object(
                api,
                "_run_openai_compatible_completion",
                return_value={
                    "answer": json.dumps({
                        "verdict": "PASS",
                        "decision": "CALL BUY",
                        "conflicting_direction": False,
                        "reason": "All checks agree.",
                    }),
                    "model": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
                    "latency_ms": 25.0,
                },
            ),
        ):
            response = self.client.post("/v1/ai/review-signal", headers=self.device_headers, json={"index": "NIFTY"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["verdict"], "PASS")
        self.assertEqual(response.json()["decision"], "CALL BUY")

        with (
            patch.object(api, "_signal_cache", payload),
            patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key", "KUMO_NVIDIA_API_KEY": ""}, clear=False),
            patch.object(
                api,
                "_run_openai_compatible_completion",
                return_value={
                    "answer": json.dumps({
                        "verdict": "PASS",
                        "decision": "PUT BUY",
                        "conflicting_direction": True,
                        "reason": "Direction conflicts.",
                    }),
                    "model": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
                    "latency_ms": 25.0,
                },
            ),
        ):
            response = self.client.post("/v1/ai/review-signal", headers=self.device_headers, json={"index": "NIFTY"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["verdict"], "WAIT")
        self.assertEqual(response.json()["decision"], "WAIT")
        self.assertFalse(response.json()["ai_direction_consistent"])
    def test_health_is_available_without_device_header(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_favicon_request_is_not_reported_as_a_missing_route(self):
        response = self.client.get("/favicon.ico")
        self.assertEqual(response.status_code, 204)

    def test_ai_validation_reports_not_configured_without_server_keys(self):
        payload = {
            "live": False,
            "market": {"NIFTY": {"ltp": None, "live": False}},
            "signals": {"NIFTY": {"decision": "WAIT", "layers": {}, "reasons": ["No fresh quote"]}},
            "generated_at": "2026-10-13T00:00:00+00:00",
        }
        with patch.object(api, "_get_signals", return_value=payload), \
             patch.dict(os.environ, {"NVIDIA_API_KEY": "", "KUMO_NVIDIA_API_KEY": "", "OPENAI_API_KEY": "", "OPENROUTER_API_KEY": ""}, clear=False):
            response = self.client.post(
                "/v1/ai/validate",
                headers=self.device_headers,
                json={"index": "NIFTY"},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["overall_status"], "BLOCKED_NO_LIVE_DATA")
        self.assertNotIn("openai", data["providers"])
        self.assertEqual(data["providers"]["openrouter"]["status"], "not_configured")
        self.assertEqual(data["deterministic_decision"], "WAIT")

    def test_ai_status_invalidates_cached_test_after_provider_configuration_changes(self):
        stale_cache = {
            'nvidia': {
                'provider': 'nvidia', 'configured': True, 'ok': True, 'status': 'ok',
                'model': 'old-model', '_config_fingerprint': 'old-key-fingerprint',
            },
        }
        with patch.dict(os.environ, {
            'NVIDIA_API_KEY': 'rotated-key', 'KUMO_NVIDIA_API_KEY': '',
            'NVIDIA_CHAT_MODEL': 'test-model',
            'NVIDIA_CHAT_BASE_URL': 'https://integrate.api.nvidia.com/v1/chat/completions',
            'OPENROUTER_API_KEY': '', 'OPEN_ROUTER_API_KEY': '',
        }, clear=False), patch.object(api, '_ai_provider_test_cache', stale_cache):
            response = self.client.get('/v1/ai/status', headers=self.device_headers)
        self.assertEqual(response.status_code, 200, response.text)
        provider = response.json()['providers']['nvidia']
        self.assertFalse(provider['ok'])
        self.assertEqual(provider['status'], 'configured_not_tested')
        self.assertNotIn('_config_fingerprint', provider)
    def test_openai_environment_key_is_ignored_by_ai_status(self):
        with patch.dict(os.environ, {
            "NVIDIA_API_KEY": "", "KUMO_NVIDIA_API_KEY": "",
            "OPENROUTER_API_KEY": "", "OPEN_ROUTER_API_KEY": "",
            "OPENAI_API_KEY": "legacy-key-must-be-ignored",
            "OPENAI_MODEL": "legacy-model-must-be-ignored",
        }, clear=False):
            response = self.client.get("/v1/ai/status", headers=self.device_headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn("openai", data["providers"])
        self.assertFalse(data["llm_configured"])
        self.assertEqual(data["provider"], "deterministic_fallback")

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

    def test_angel_connect_returns_safe_smartapi_auth_error_code(self):
        class FailingAdapter:
            def __init__(self, credentials):
                pass

            def profile(self):
                raise RuntimeError("Angel One SmartAPI error (AB1050): Invalid totp")

        with patch.object(api, "_adapter", None), \
             patch.object(api, "_load_credentials", return_value={}), \
             patch.object(api, "_credentials_from_env", return_value={}), \
             patch.object(api, "_forget_credentials"), \
             patch.object(api, "AngelOneReadOnly", FailingAdapter):
            response = self.client.post(
                "/v1/angel/connect",
                headers=self.device_headers,
                json={
                    "angel_api_key": "test-api-key",
                    "angel_client_code": "test-client",
                    "angel_pin": "test-pin",
                    "angel_totp": "123456",
                    "remember_credentials": False,
                },
            )
        self.assertEqual(response.status_code, 502)
        detail = response.json()["detail"]
        self.assertEqual(detail["stage"], "smartapi_authentication")
        self.assertEqual(detail["error_code"], "AB1050")
        self.assertEqual(detail["broker_message"], "Invalid totp")
        self.assertNotIn("test-api-key", response.text)
        self.assertNotIn("test-pin", response.text)
        self.assertNotIn("123456", response.text)

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

    def test_indicator_snapshot_uses_repository_technical_helpers(self):
        closes = [100.0 + index * 0.25 for index in range(60)]
        candles = [
            [f"2026-10-12T{9 + (index // 12):02d}:{(index % 12) * 5:02d}:00+05:30",
             close, close + 1.0, close - 1.0, close, 1000.0]
            for index, close in enumerate(closes)
        ]
        indicators = api._indicator_snapshot(closes, candles, candles[-20:])
        self.assertIsNotNone(indicators["ema_fast_8"])
        self.assertIsNotNone(indicators["ema_slow_21"])
        self.assertIsNotNone(indicators["sma_20"])
        self.assertIsNotNone(indicators["sma_50"])
        self.assertIsNotNone(indicators["rsi_14"])
        self.assertIsNotNone(indicators["underlying_atr_14"])
        self.assertIsNotNone(indicators["vwap"])
        # Flutter pages consume these stable aliases; older backend keys alone
        # made Dashboard/Market/Indicators appear blank despite valid candles.
        self.assertEqual(indicators["ema_fast"], indicators["ema_fast_8"])
        self.assertEqual(indicators["ema_slow"], indicators["ema_slow_21"])
        self.assertEqual(indicators["rsi14"], indicators["rsi_14"])
        self.assertEqual(indicators["atr14"], indicators["underlying_atr_14"])
        self.assertIn("bb_upper", indicators)
        self.assertIn("stochastic_k14", indicators)

    def test_backtest_accepts_flutter_form_payload(self):
        request = api.BacktestRequest(
            index="NIFTY",
            from_date="2026-10-01",
            to_date="2026-10-05",
            interval="FIVE_MINUTE",
            fast_ema=8,
            slow_ema=13,
            atr_period=14,
            stop_atr=1.5,
            target_r=2.0,
            max_hold_bars=30,
            slippage_r=0.02,
            transaction_cost_r=0.02,
        )
        self.assertEqual(request.index, "NIFTY")
        self.assertEqual(request.fast_ema, 8)
        self.assertEqual(request.from_date, "2026-10-01")

    def test_historical_backtest_returns_flutter_report_shape(self):
        start = datetime(2026, 10, 1, 9, 15, tzinfo=timezone.utc)
        closes = [150 - i for i in range(30)]
        closes += [120 + i for i in range(30)]
        closes += [150 - i for i in range(40)]
        candles = []
        for index, close in enumerate(closes):
            stamp = (start + timedelta(minutes=5 * index)).isoformat()
            candles.append([stamp, close, close + 1, close - 1, close, 1000])
        class FakeAdapter:
            def candles(self, exchange, token, interval, fromdate, todate):
                self.last_request = (exchange, token, interval, fromdate, todate)
                return {"candles": candles}

        with patch.object(api, "_require_adapter", return_value=FakeAdapter()):
            response = self.client.post(
                "/v1/backtest/historical",
                headers=self.device_headers,
                json={
                    "index": "NIFTY", "from_date": "2026-10-01", "to_date": "2026-10-02",
                    "interval": "FIVE_MINUTE", "fast_ema": 8, "slow_ema": 13,
                    "atr_period": 14, "stop_atr": 1.5, "target_r": 2.0,
                    "max_hold_bars": 30, "slippage_r": 0.02, "transaction_cost_r": 0.02,
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()["report"]
        self.assertEqual(report["candle_count"], 100)
        self.assertIn("metrics", report)
        self.assertIn("trades", report)
        self.assertIn("n", report["metrics"])
        self.assertTrue(report["assumptions"])

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

    def test_shared_workspace_endpoints_do_not_404_or_claim_fake_data(self):
        ai = self.client.get("/v1/ai/status", headers=self.device_headers)
        self.assertEqual(ai.status_code, 200, ai.text)
        self.assertIn("status", ai.json())
        search = self.client.post("/v1/providers/search/status", headers=self.device_headers, json={})
        self.assertEqual(search.status_code, 200, search.text)
        self.assertIn("exa", search.json()["providers"])
        orders = self.client.get("/v1/live/orders", headers=self.device_headers)
        self.assertEqual(orders.status_code, 200, orders.text)
        self.assertFalse(orders.json()["order_placement_enabled"])
        self.assertEqual(orders.json()["orders"], [])
        portfolio = self.client.get("/v1/portfolio", headers=self.device_headers)
        self.assertEqual(portfolio.status_code, 200, portfolio.text)
        self.assertEqual(portfolio.json()["status"], "not_connected")
        self.assertEqual(portfolio.json()["positions"], [])

    def test_ai_chat_fallback_uses_real_payload_fields_and_discloses_no_llm(self):
        payload = {
            "market": {"NIFTY": {"ltp": 25000.0, "age_seconds": 3, "live": True}},
            "signals": {"NIFTY": {"decision": "WAIT", "reasons": ["missing option evidence"], "live_validation": {"verdict": "WARN"}}},
        }
        with patch.object(api, "_get_signals", return_value=payload), \
             patch.dict(os.environ, {"NVIDIA_API_KEY": "", "KUMO_NVIDIA_API_KEY": "", "OPENAI_API_KEY": "", "OPENROUTER_API_KEY": ""}, clear=False):
            response = self.client.post(
                "/v1/ai/chat",
                headers=self.device_headers,
                json={"index": "NIFTY", "question": "Explain the current signal", "history": []},
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertFalse(body["llm_used"])
        self.assertEqual(body["provider"], "deterministic_fallback")
        self.assertIn("25000.0", body["answer"])
        self.assertIn("missing option evidence", body["answer"])

    def test_signals_and_ai_chat_consume_the_same_shared_signal_snapshot(self):
        snapshot = {
            "generated_at": "2026-10-14T02:00:00+00:00",
            "market": {"NIFTY": {"ltp": 25000.0, "source": "angelone_smartapi", "live": False}},
            "signals": {
                "NIFTY": {
                    "decision": "WAIT",
                    "quant_engine": {"decision": "WAIT", "passed_layers": 1},
                    "five_layer_engine": {"decision": "WAIT", "passed_layers": 1},
                    "live_validation": {"verdict": "WAIT", "blocks": ["STALE_MARKET_DATA"]},
                    "reasons": ["STALE_MARKET_DATA"],
                }
            },
        }
        with patch.object(api, "_get_signals", return_value=snapshot), \
             patch.dict(os.environ, {
                 "NVIDIA_API_KEY": "", "KUMO_NVIDIA_API_KEY": "",
                 "OPENROUTER_API_KEY": "", "OPEN_ROUTER_API_KEY": "",
             }, clear=False):
            signals_response = self.client.get("/v1/signals", headers=self.device_headers)
            chat_response = self.client.post(
                "/v1/ai/chat", headers=self.device_headers,
                json={"index": "NIFTY", "question": "Explain the current signal", "history": []},
            )
        self.assertEqual(signals_response.status_code, 200, signals_response.text)
        self.assertEqual(chat_response.status_code, 200, chat_response.text)
        signal = signals_response.json()["signals"]["NIFTY"]
        chat_signal = chat_response.json()["signal"]
        self.assertEqual(chat_signal["decision"], signal["decision"])
        self.assertEqual(chat_signal["quant_engine"]["decision"], signal["quant_engine"]["decision"])
        self.assertEqual(chat_signal["five_layer_engine"]["decision"], signal["five_layer_engine"]["decision"])
        self.assertEqual(chat_signal["live_validation"]["verdict"], signal["live_validation"]["verdict"])
        self.assertEqual(signal["decision"], "WAIT")

    def test_kumo_key_does_not_configure_nvidia_chat(self):
        payload = {
            "market": {"NIFTY": {"ltp": 25000.0, "age_seconds": 3, "live": True}},
            "signals": {"NIFTY": {"decision": "WAIT", "reasons": ["risk gate wait"]}},
        }
        with patch.object(api, "_get_signals", return_value=payload), \
             patch.dict(os.environ, {
                 "NVIDIA_API_KEY": "", "KUMO_NVIDIA_API_KEY": "kumo-only-key",
                 "OPENROUTER_API_KEY": "", "OPEN_ROUTER_API_KEY": "",
             }, clear=False), \
             patch.object(api, "_run_openai_compatible_completion") as completion:
            status = self.client.get("/v1/ai/status", headers=self.device_headers)
            response = self.client.post(
                "/v1/ai/chat", headers=self.device_headers,
                json={"index": "NIFTY", "question": "Explain the current signal", "history": []},
            )
        self.assertEqual(status.status_code, 200, status.text)
        self.assertFalse(status.json()["providers"]["nvidia"]["configured"])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["provider"], "deterministic_fallback")
        self.assertFalse(response.json()["llm_used"])
        completion.assert_not_called()

    def test_ai_chat_uses_openrouter_when_nvidia_is_unconfigured(self):
        payload = {"market": {"NIFTY": {
                       "ltp": 25000.0, "age_seconds": 3, "live": True,
                       "strategy_suite": {"signal": "WAIT", "trace": {
                           "execution_id": "strategy-test", "strategy_version": "strategy-suite-v1",
                           "input_candle_count": 35, "input_sha256": "a" * 64,
                       }},
                   }},
                   "signals": {"NIFTY": {"decision": "WAIT", "reasons": ["risk gate wait"]}}}
        with patch.object(api, "_get_signals", return_value=payload), \
             patch.dict(os.environ, {"NVIDIA_API_KEY": "", "KUMO_NVIDIA_API_KEY": "",
                                      "OPENROUTER_API_KEY": "unit-test-key", "OPENROUTER_MODEL": "router-test"}, clear=False), \
             patch.object(api, "_run_openai_compatible_completion", return_value={
                 "answer": "Distinct test response", "provider": "openrouter", "model": "router-test",
                 "llm_used": True, "ok": True, "status": "connected", "latency_ms": 12.0,
             }) as completion:
            response = self.client.post("/v1/ai/chat", headers=self.device_headers,
                                        json={"index": "NIFTY", "question": "Explain only the risk gate", "history": []})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["provider"], "openrouter")
        self.assertTrue(body["llm_used"])
        self.assertEqual(body["answer"], "Distinct test response")
        self.assertTrue(body["strategy_consumption_trace"]["ai_context_sent"])
        self.assertEqual(body["strategy_consumption_trace"]["execution_id"], "strategy-test")
        self.assertEqual(body["strategy_consumption_trace"]["ai_provider"], "openrouter")
        self.assertFalse(body["strategy_consumption_trace"]["ai_semantic_use_verifiable"])
        completion.assert_called_once()

    def test_ai_chat_falls_back_to_openrouter_when_nvidia_fails(self):
        payload = {"market": {"NIFTY": {"ltp": 25000.0, "age_seconds": 3, "live": True}},
                   "signals": {"NIFTY": {"decision": "WAIT", "reasons": ["risk gate wait"]}}}
        with patch.object(api, "_get_signals", return_value=payload), \
             patch.dict(os.environ, {"NVIDIA_API_KEY": "nvidia-test-key", "KUMO_NVIDIA_API_KEY": "",
                                      "OPENROUTER_API_KEY": "router-test-key", "OPENROUTER_MODEL": "router-test"}, clear=False), \
             patch.object(api, "_run_openai_compatible_completion", side_effect=[
                 RuntimeError("nvidia_http_503"),
                 {"answer": "Router fallback response", "provider": "openrouter", "model": "router-test",
                  "llm_used": True, "ok": True, "status": "connected", "latency_ms": 15.0},
             ]) as completion:
            response = self.client.post("/v1/ai/chat", headers=self.device_headers,
                                        json={"index": "NIFTY", "question": "Explain the current wait", "history": []})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["provider"], "openrouter")
        self.assertEqual(body["answer"], "Router fallback response")
        self.assertEqual(body["provider_failures"][0]["status"], "nvidia_http_503")
        self.assertEqual(completion.call_count, 2)
        

    def test_ai_chat_can_read_mcX_commodity_snapshot(self):
        payload = {
            "market": {},
            "signals": {},
            "commodities": [{
                "name": "CRUDEOILM", "symbol": "CRUDEOILM26OCTFUT",
                "ltp": 5500.0, "age_seconds": 2.0, "live": True,
                "source": "angelone_smartapi", "decision": "WAIT",
                "reasons": ["commodity options require verified Greeks and risk inputs"],
            }],
        }
        with patch.object(api, "_get_signals", return_value=payload), \
             patch.dict(os.environ, {"NVIDIA_API_KEY": "", "KUMO_NVIDIA_API_KEY": "", "OPENAI_API_KEY": "", "OPENROUTER_API_KEY": ""}, clear=False):
            response = self.client.post(
                "/v1/ai/chat", headers=self.device_headers,
                json={"index": "CRUDEOILM", "question": "Analyze current MCX context", "history": []},
            )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertFalse(data["llm_used"])
        self.assertEqual(data["index"], "CRUDEOILM")
        self.assertIn("5500.0", data["answer"])
        self.assertIn("verified Greeks", data["answer"])

    def test_ai_chat_uses_nvidia_only_when_configured(self):
        payload = {
            "market": {"NIFTY": {"ltp": 25000.0, "age_seconds": 3, "live": True, "source": "angelone_smartapi"}},
            "signals": {"NIFTY": {"decision": "WAIT", "reasons": ["risk gate"], "live_validation": {"verdict": "WARN"}}},
        }

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self):
                return json.dumps({"choices": [{"message": {"content": "Snapshot reviewed; risk gate remains WAIT."}}]}).encode()

        with patch.object(api, "_get_signals", return_value=payload), \
             patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key", "NVIDIA_CHAT_MODEL": "nvidia/llama-3.3-nemotron-super-49b-v1.5", "KUMO_NVIDIA_API_KEY": "", "OPENAI_API_KEY": "openai-key-must-not-be-used", "OPENAI_MODEL": "gpt-4o-mini", "OPENROUTER_API_KEY": "router-key-must-not-be-used"}, clear=False), \
             patch.object(api.urllib.request, "urlopen", return_value=FakeResponse()):
            response = self.client.post(
                "/v1/ai/chat", headers=self.device_headers,
                json={"index": "NIFTY", "question": "Explain the current signal", "history": []},
            )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertTrue(data["llm_used"])
        self.assertEqual(data["provider"], "nvidia")
        self.assertEqual(data["answer"], "Snapshot reviewed; risk gate remains WAIT.")
        self.assertFalse(data["order_placement_enabled"])

    def test_search_provider_test_uses_live_provider_checks(self):
        fake_evidence = {
            "provider_checks": {
                "exa": {"configured": True, "ok": False, "status": "authentication_failed", "result_count": 0},
                "tavily": {"configured": True, "ok": True, "status": "ok", "result_count": 2},
            },
            "articles": [{"title": "source-backed headline", "url": "https://example.com", "source": "tavily"}],
            "errors": ["exa_authentication_failed"],
        }
        with patch.dict(os.environ, {"EXA_API_KEY": "exa-test", "TAVILY_API_KEY": "tavily-test"}, clear=False), \
             patch.object(api, "fetch_market_news_sentiment", return_value=fake_evidence) as fetch:
            response = self.client.post("/v1/providers/search/test", headers=self.device_headers)
        self.assertEqual(response.status_code, 200, response.text)
        fetch.assert_called_once()
        self.assertTrue(fetch.call_args.kwargs["force"])
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertFalse(data["providers"]["exa"]["ok"])
        self.assertTrue(data["providers"]["tavily"]["ok"])
        self.assertEqual(data["providers"]["exa"]["status"], "authentication_failed")

    def test_quotes_split_large_same_exchange_batches_to_smartapi_limit(self):
        class FakeAdapter:
            def __init__(self):
                self.batch_sizes = []
            def market_data(self, mode, exchange_tokens):
                tokens = exchange_tokens["MCX"]
                self.batch_sizes.append(len(tokens))
                return {"rows": [{"symbolToken": token, "ltp": 1.0} for token in tokens]}

        adapter = FakeAdapter()
        with patch.object(api, "_stream", None), \
             patch.object(api, "_quote_rows", side_effect=lambda result: result["rows"]):
            result = api._quotes(adapter, "MCX", [str(i) for i in range(101)])
        self.assertEqual(adapter.batch_sizes, [50, 50, 1])
        self.assertEqual(len(result), 101)

    def test_paper_trade_open_close_and_report_deduct_costs(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(api, "_paper_trade_path", return_value=Path(tmp) / "paper.json"):
            api._paper_trades_memory.clear()
            opened = self.client.post(
                "/v1/paper/trades/open",
                headers=self.device_headers,
                json={
                    "trade_id": "test-paper-trade", "strategy_id": "unit-test",
                    "index": "NIFTY", "side": "CALL BUY", "regime": "TEST",
                    "slippage_r": 0.02, "transaction_cost_r": 0.02,
                    "notes": "No broker order",
                },
            )
            self.assertEqual(opened.status_code, 200, opened.text)
            closed = self.client.post(
                "/v1/paper/trades/test-paper-trade/close",
                headers=self.device_headers,
                json={"gross_r": 1.0, "notes": "test result"},
            )
            self.assertEqual(closed.status_code, 200, closed.text)
            self.assertEqual(closed.json()["trade"]["net_r"], 0.96)
            report = self.client.get("/v1/paper/report", headers=self.device_headers)
            self.assertEqual(report.status_code, 200, report.text)
            self.assertEqual(report.json()["metrics"]["trade_count"], 1)
            self.assertEqual(report.json()["metrics"]["net_total_r"], 0.96)
            api._paper_trades_memory.clear()

    def test_index_quote_survives_signal_pipeline_failure(self):
        # The test verifies fallback quote preservation, not the host runner's
        # wall-clock market session. Freeze the session as open for determinism.
        quote = {
            "ltp": 25000.0,
            "exchange_timestamp": api._utc_now().isoformat(),
            "best5Data": {
                "buy": [{"price": 24999.5, "quantity": 10}],
                "sell": [{"price": 25000.5, "quantity": 12}],
            },
        }
        with (
            patch.object(api, "_signal_cache", None),
            patch.object(api, "_signal_cache_at", 0),
            patch.object(api, "_require_adapter", return_value=object()),
            patch.object(api, "_load_master", return_value=[]),
            patch.object(api, "_start_stream"),
            patch.object(api, "_schedule_news_refresh"),
            patch.object(api, "_index_snapshot", side_effect=RuntimeError("insufficient candle history")),
            patch.object(api, "_quotes", side_effect=lambda adapter, exchange, tokens: {tokens[0]: quote}),
            patch.object(api, "_commodity_snapshot", return_value=[]),
            patch.object(api, "_stream", None),
            patch.object(api, "_is_market_session_open", return_value=True),
        ):
            result = api._get_signals_uncached(force=True)
        self.assertEqual(result["market"]["NIFTY"]["ltp"], 25000.0)
        self.assertTrue(result["market"]["NIFTY"]["live"])
        self.assertEqual(result["signals"]["NIFTY"]["decision"], "WAIT")
        self.assertIn("insufficient candle history", result["market"]["NIFTY"]["signal_error"])

    def test_strategy_inputs_exclude_incomplete_five_minute_candle(self):
        now = datetime.fromisoformat("2026-10-14T04:05:30+00:00")
        rows = [
            {"timestamp": "2026-10-14T04:00:00+00:00", "close": 100.0},
            {"timestamp": "2026-10-14T04:05:00+00:00", "close": 101.0},
        ]
        completed = api._completed_candle_rows(rows, timeframe_minutes=5, now=now)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["close"], 100.0)

    def test_stale_signal_snapshot_clears_actionable_levels(self):
        cached = {
            "signals": {
                "NIFTY": {
                    "decision": "CALL BUY", "strike": 25000, "expiry": "2026-10-29",
                    "entry": 100.0, "exit": 115.0, "stop_loss": 95.0, "target": 115.0,
                    "option_type": "CALL", "option_side": "CE",
                    "trade_plan": {
                        "selection_grade": "A", "strike": 25000, "expiry": "2026-10-29",
                        "entry": 100.0, "exit": 115.0, "stop_loss": 95.0, "target": 115.0,
                    },
                    "live_validation": {"verdict": "PASS", "blocks": []},
                    "five_layer_engine": {"decision": "CALL BUY", "entry": 101.0, "stop_loss": 96.0, "target": 118.0},
                    "quant_engine": {"decision": "CALL BUY", "trade_plan": {"strike": 25000, "entry": 102.0}},
                    "strategy_filter": {"pass": True, "state": "PASS"},
                    "signal_stability": {"state": "CONFIRMED"},
                }
            },
            "market": {"NIFTY": {"ltp": 25000.0, "live": True}},
            "commodities": [{
                "name": "CRUDEOIL", "decision": "CALL BUY", "strike": 6200,
                "entry": 6200.0, "stop_loss": 6150.0, "target": 6300.0,
                "quant_engine": {"decision": "CALL BUY", "target": 6350.0},
            }],
            "trade_plans": [{"index": "NIFTY"}],
            "qualified_trade_count": 1,
        }
        stale = api._stale_signal_snapshot(cached, 75.0)
        signal = stale["signals"]["NIFTY"]
        self.assertEqual(signal["decision"], "WAIT")
        self.assertEqual(signal["candidate_decision"], "CALL BUY")
        self.assertFalse(signal["data_fresh"])
        for key in ("strike", "expiry", "entry", "exit", "stop_loss", "target", "option_type", "option_side"):
            self.assertIsNone(signal[key])
        self.assertEqual(signal["trade_plan"]["selection_grade"], "WAIT")
        self.assertEqual(signal["five_layer_engine"]["decision"], "WAIT")
        self.assertIsNone(signal["five_layer_engine"]["entry"])
        self.assertIsNone(signal["five_layer_engine"]["stop_loss"])
        self.assertIsNone(signal["five_layer_engine"]["target"])
        self.assertEqual(signal["quant_engine"]["decision"], "WAIT")
        self.assertIsNone(signal["quant_engine"]["trade_plan"]["strike"])
        self.assertIsNone(signal["quant_engine"]["trade_plan"]["entry"])
        commodity = stale["commodities"][0]
        self.assertEqual(commodity["decision"], "WAIT")
        self.assertFalse(commodity["live"])
        self.assertIsNone(commodity["strike"])
        self.assertIsNone(commodity["entry"])
        self.assertIsNone(commodity["stop_loss"])
        self.assertIsNone(commodity["target"])
        self.assertEqual(commodity["quant_engine"]["decision"], "WAIT")
        self.assertIsNone(commodity["quant_engine"]["target"])
        self.assertFalse(signal["strategy_filter"]["pass"])
        self.assertEqual(signal["signal_stability"]["state"], "BLOCKED_BY_STALE_DATA")
        self.assertEqual(stale["trade_plans"], [])
        self.assertEqual(stale["qualified_trade_count"], 0)
        self.assertEqual(cached["signals"]["NIFTY"]["decision"], "CALL BUY")

    def test_cold_signal_request_returns_wait_while_refresh_runs_in_background(self):
        metrics = {"last_duration_ms": None, "build_count": 0, "in_flight": False, "last_error": None}
        with patch.object(api, "_signal_cache", None), \
             patch.object(api, "_signal_cache_at", 0), \
             patch.object(api, "_signal_build_metrics", metrics), \
             patch.object(api.threading, "Thread") as thread:
            result = api._get_signals(force=True)
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()
        self.assertTrue(result["refreshing"])
        self.assertFalse(result["live"])
        self.assertIn("loading in the background", result["message"])

    def test_ai_probe_cannot_pass_stale_market_data(self):
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                model_output = json.dumps({"verdict": "PASS", "reason": "looks good"})
                return json.dumps({"choices": [{"message": {"content": model_output}}]}).encode("utf-8")

        with patch.object(api.urllib.request, "urlopen", return_value=FakeResponse()):
            result = api._run_ai_validation_probe(
                "openrouter", "test-secret", "test-model", "https://openrouter.ai/api/v1/chat/completions",
                {"source": "angelone_smartapi", "source_timestamp": "2026-10-13T09:00:00+00:00",
                 "ltp": 25000.0, "age_seconds": 120.0, "live": False},
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["verdict"], "WAIT")
        self.assertNotIn("test-secret", str(result))


    def test_ai_provider_rate_limit_is_reported_as_rate_limited_not_bad_json(self):
        from email.message import Message
        headers = Message()
        headers["Retry-After"] = "30"
        error = api.urllib.error.HTTPError(
            "https://openrouter.ai/api/v1/chat/completions", 429, "Too Many Requests", headers, None
        )
        with patch.object(api.urllib.request, "urlopen", side_effect=error):
            result = api._run_ai_validation_probe(
                "openrouter", "test-secret", "test-model", "https://openrouter.ai/api/v1/chat/completions",
                {"source": "angelone_smartapi", "source_timestamp": "2026-10-13T09:00:00+00:00",
                 "ltp": 25000.0, "age_seconds": 2.0, "live": True},
            )
        self.assertEqual(result["status"], "rate_limited")
        self.assertEqual(result["retry_after_seconds"], "30")
        self.assertEqual(result["verdict"], "WAIT")
        self.assertNotIn("test-secret", str(result))

    def test_mcx_option_chain_returns_broker_ce_pe_quotes_without_fabricated_greeks(self):
        expiry = (api.datetime.now(api.IST).date() + api.timedelta(days=7)).strftime("%d%b%Y").upper()
        rows = [
            {"exch_seg": "MCX", "name": "CRUDEOIL", "symbol": f"CRUDEOIL{expiry}FUT",
             "instrumenttype": "FUTCOM", "token": "mcx-future", "expiry": expiry},
            {"exch_seg": "MCX", "name": "CRUDEOIL", "symbol": f"CRUDEOIL{expiry}550000CE",
             "instrumenttype": "OPTFUT", "token": "mcx-call", "expiry": expiry, "strike": "550000"},
            {"exch_seg": "MCX", "name": "CRUDEOIL", "symbol": f"CRUDEOIL{expiry}550000PE",
             "instrumenttype": "OPTFUT", "token": "mcx-put", "expiry": expiry, "strike": "550000"},
        ]
        stamp = api._utc_now().isoformat()
        quotes = {
            "mcx-future": {"ltp": 5500.0, "exchange_timestamp": stamp},
            "mcx-call": {"ltp": 100.0, "exchange_timestamp": stamp,
                         "best5Data": {"buy": [{"price": 99.5, "quantity": 20}],
                                       "sell": [{"price": 100.5, "quantity": 25}]}},
            "mcx-put": {"ltp": 110.0, "exchange_timestamp": stamp,
                        "best5Data": {"buy": [{"price": 109.5, "quantity": 18}],
                                      "sell": [{"price": 110.5, "quantity": 22}]}},
        }
        with (
            patch.object(api, "_require_adapter", return_value=object()),
            patch.object(api, "_load_master", return_value=rows),
            patch.object(api, "_quotes", side_effect=lambda _adapter, _exchange, tokens: {
                token: quotes[token] for token in tokens if token in quotes
            }),
        ):
            response = self.client.get("/v1/option-chain?index=CRUDEOIL", headers=self.device_headers)

        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["source"], "angelone_smartapi")
        self.assertEqual(data["underlying_type"], "MCX_FUTURE")
        sides = {row["side"] for row in data["option_chain"]}
        self.assertEqual(sides, {"CE", "PE"})
        self.assertTrue(all(row["timestamp"] == stamp for row in data["option_chain"]))
        self.assertTrue(all(row["delta"] is None and row["iv"] is None for row in data["option_chain"]))

    def test_commodity_footprint_uses_mcx_future_and_symbol_specific_price_step(self):
        expiry = (api.datetime.now(api.IST).date() + api.timedelta(days=7)).strftime("%d%b%Y").upper()
        rows = [
            {"exch_seg": "MCX", "name": "CRUDEOIL", "symbol": f"CRUDEOILM{expiry}FUT",
             "instrumenttype": "FUTCOM", "token": "987654", "expiry": expiry},
        ]
        contract = api._find_nearest_future(rows, "CRUDEOILM")
        self.assertIsNotNone(contract)
        self.assertEqual(contract["exchange"], "MCX")
        self.assertEqual(contract["token"], "987654")
        self.assertEqual(api._footprint_chart_step("CRUDEOILM"), 1.0)
        self.assertEqual(api._footprint_chart_step("NATURALGAS"), 0.5)
        self.assertEqual(api._footprint_chart_step("NIFTY"), 5.0)

    def test_footprint_levels_use_only_broker_best5_depth(self):
        quote = {
            "best5Data": {
                "buy": [{"price": 24999.5, "quantity": 10, "orders": 2}],
                "sell": [{"price": 25000.5, "quantity": 12, "orders": 3}],
            }
        }
        levels, buy_orders, sell_orders = api._footprint_levels(quote, step=5.0)
        self.assertEqual(levels, {"25000.00": [12.0, 10.0]})
        self.assertEqual(buy_orders, 2)
        self.assertEqual(sell_orders, 3)
        self.assertEqual(api._footprint_levels({}, step=5.0), ({}, 0, 0))

    def test_option_chain_returns_short_cache_hit_without_broker_call(self):
        payload = {
            "index": "NIFTY", "contracts": [], "option_chain": [],
            "observed_at": "2026-10-14T00:00:00+00:00", "signal_only": True,
        }
        cache_entry = (api.time.monotonic(), payload)
        with patch.dict(api._option_chain_cache, {"NIFTY": cache_entry}, clear=False):
            with patch.object(api, "OPTION_CHAIN_CACHE_TTL_SECONDS", 2.0):
                with patch.object(api, "_require_adapter", side_effect=AssertionError("cache miss")):
                    response = self.client.get("/v1/option-chain?index=NIFTY", headers=self.device_headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["cache"]["hit"])
        self.assertLess(response.json()["request_elapsed_ms"], 100)

    def test_market_intelligence_refresh_uses_exa_tavily_and_nvidia(self):
        previous_state = dict(api._market_intel_state)

        def fake_news(index, exa_api_key=None, tavily_api_key=None, force=False):
            self.assertTrue(force)
            return {
                "status": "ok",
                "label": "MIXED",
                "score": 0.1,
                "article_count": 1,
                "sources": ["exa", "tavily"],
                "observed_at": "2026-10-14T10:00:00+00:00",
                "provider_checks": {
                    "exa": {"configured": True, "ok": True, "result_count": 1, "status": "ok"},
                    "tavily": {"configured": True, "ok": True, "result_count": 1, "status": "ok"},
                },
                "articles": [{
                    "title": f"{index} source-backed market headline",
                    "url": f"https://example.com/{index.lower()}",
                    "published_at": "2026-10-14T09:55:00+00:00",
                    "source": "exa",
                    "content": "A test headline with no actionable trade claim.",
                }],
            }

        try:
            with patch.dict(os.environ, {
                "EXA_API_KEY": "exa-test",
                "TAVILY_API_KEY": "tavily-test",
                "NVIDIA_API_KEY": "nvidia-test",
                "NVIDIA_CHAT_MODEL": "test-nvidia-model",
            }, clear=False), \
                 patch.object(api, "fetch_market_news_sentiment", side_effect=fake_news) as fetch, \
                 patch.object(api, "_run_openai_compatible_completion", return_value={
                     "answer": "Source-backed test market brief.",
                     "provider": "nvidia",
                     "model": "test-nvidia-model",
                     "llm_used": True,
                     "ok": True,
                     "status": "connected",
                     "latency_ms": 12.0,
                 }) as inference:
                api._refresh_market_intelligence_once()
                state = dict(api._market_intel_state)

            self.assertEqual(fetch.call_count, len(api.INDEXES) + 1)  # six indexes plus MCX
            self.assertTrue(all(call.kwargs.get("force") is True for call in fetch.call_args_list))
            self.assertEqual(state["status"], "READY")
            self.assertEqual(state["summary"], "Source-backed test market brief.")
            self.assertEqual(state["summary_provider"], "nvidia")
            self.assertEqual(state["refresh_interval_seconds"], 900)
            self.assertGreaterEqual(len(state["articles"]), len(api.INDEXES))
            self.assertEqual(inference.call_count, 1)
            self.assertFalse(state["order_placement_enabled"])
        finally:
            with api._market_intel_lock:
                api._market_intel_state = previous_state
                api._market_intel_refreshing = False

if __name__ == "__main__":
    unittest.main()
