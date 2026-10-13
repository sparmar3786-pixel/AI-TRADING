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
        with patch.object(api, "_get_signals", return_value=payload):
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

    def test_index_quote_survives_signal_pipeline_failure(self):
        quote = {
            "ltp": 25000.0,
            "exchange_timestamp": api._utc_now().isoformat(),
            "best5Data": {
                "buy": [{"price": 24999.5, "quantity": 10}],
                "sell": [{"price": 25000.5, "quantity": 12}],
            },
        }
        with patch.object(api, "_signal_cache", None), \
             patch.object(api, "_signal_cache_at", 0), \
             patch.object(api, "_require_adapter", return_value=object()), \
             patch.object(api, "_load_master", return_value=[]), \
             patch.object(api, "_start_stream"), \
             patch.object(api, "_schedule_news_refresh"), \
             patch.object(api, "_index_snapshot", side_effect=RuntimeError("insufficient candle history")), \
             patch.object(api, "_quotes", side_effect=lambda adapter, exchange, tokens: {tokens[0]: quote}), \
             patch.object(api, "_commodity_snapshot", return_value=[]), \
             patch.object(api, "_stream", None):
            result = api._get_signals_uncached(force=True)
        self.assertEqual(result["market"]["NIFTY"]["ltp"], 25000.0)
        self.assertTrue(result["market"]["NIFTY"]["live"])
        self.assertEqual(result["signals"]["NIFTY"]["decision"], "WAIT")
        self.assertIn("insufficient candle history", result["market"]["NIFTY"]["signal_error"])


if __name__ == "__main__":
    unittest.main()
