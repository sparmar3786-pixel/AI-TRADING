import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import main as api
from backend.app.api_auth import AuthenticationError, authenticate_request, require_authenticated_device
from backend.app.exchange_calendar import day_status, _parse_date_cell


class AuditRemediationTests(unittest.TestCase):
    def setUp(self):
        self._mode = patch.dict(os.environ, {
            "API_AUTH_MODE": "legacy",
            "API_ACCESS_KEY": "",
            "BACKEND_ACCESS_KEY": "",
            "FIREBASE_PROJECT_ID": "",
            "GOOGLE_CLOUD_PROJECT": "",
            "AUTH_ALLOWED_UIDS": "",
        })
        self._mode.start()
        self.addCleanup(self._mode.stop)

    def test_access_key_is_required_and_constant_time_checked_in_required_mode(self):
        secret = "test-only-long-random-access-key-1234567890"
        with patch.dict(os.environ, {"API_AUTH_MODE": "required", "API_ACCESS_KEY": secret}, clear=False):
            with self.assertRaises(AuthenticationError):
                authenticate_request(access_key="")
            with self.assertRaises(AuthenticationError):
                authenticate_request(access_key="not-the-key")
            self.assertEqual(authenticate_request(access_key=secret)["method"], "access_key")

    def test_short_configured_access_key_fails_closed(self):
        from backend.app.api_auth import AuthConfigurationError
        with patch.dict(os.environ, {"API_AUTH_MODE": "required", "API_ACCESS_KEY": "short"}, clear=False):
            with self.assertRaises(AuthConfigurationError):
                authenticate_request(access_key="short")

    def test_firebase_id_token_requires_allowlisted_uid(self):
        secret_project = {
            "API_AUTH_MODE": "required",
            "API_ACCESS_KEY": "",
            "BACKEND_ACCESS_KEY": "",
            "FIREBASE_PROJECT_ID": "ai-trading-test",
            "AUTH_ALLOWED_UIDS": "owner-uid",
        }
        with patch.dict(os.environ, secret_project, clear=False):
            with patch("google.oauth2.id_token.verify_firebase_token", return_value={"user_id": "owner-uid"}):
                result = authenticate_request(authorization="Bearer signed-token")
                self.assertEqual(result, {"method": "firebase_id_token", "subject": "owner-uid"})
            with patch("google.oauth2.id_token.verify_firebase_token", return_value={"user_id": "other-user"}):
                with self.assertRaises(AuthenticationError):
                    authenticate_request(authorization="Bearer signed-token")

    def test_direct_device_helper_call_does_not_receive_fastapi_header_objects(self):
        # Nested FastAPI routers invoke api._device(x_device_id) directly.
        # Annotated headers must keep plain-string Python defaults in that path.
        device_id = "A" * 43
        self.assertEqual(api._device(device_id), device_id)

    def test_metadata_rejects_forged_device_id_without_server_auth(self):
        secret = "test-only-long-random-access-key-1234567890"
        client = TestClient(api.app)
        with patch.dict(os.environ, {"API_AUTH_MODE": "required", "API_ACCESS_KEY": secret}, clear=False):
            response = client.get("/v1/metadata", headers={"X-Device-Id": "A" * 43})
            self.assertEqual(response.status_code, 401)
            accepted = client.get("/v1/metadata", headers={
                "X-Device-Id": "A" * 43,
                "X-API-Access-Key": secret,
            })
            self.assertEqual(accepted.status_code, 200, accepted.text)


    def test_firebase_device_namespace_is_scoped_to_verified_uid(self):
        import hashlib

        device_id = "A" * 43
        with patch.dict(os.environ, {
            "API_AUTH_MODE": "required",
            "API_ACCESS_KEY": "",
            "FIREBASE_PROJECT_ID": "audit-test-project",
            "AUTH_ALLOWED_UIDS": "owner-a,owner-b",
        }, clear=False):
            with patch("google.oauth2.id_token.verify_firebase_token", return_value={"user_id": "owner-a"}):
                owner_a = require_authenticated_device(device_id, "", "Bearer signed-token")
            with patch("google.oauth2.id_token.verify_firebase_token", return_value={"user_id": "owner-b"}):
                owner_b = require_authenticated_device(device_id, "", "Bearer signed-token")

        self.assertNotEqual(owner_a, owner_b)
        self.assertEqual(
            owner_a,
            hashlib.sha256(f"firebase:owner-a\\0{device_id}".encode("utf-8")).hexdigest(),
        )

    def test_secondary_routers_reject_device_id_without_server_auth(self):
        secret = "test-only-long-random-access-key-1234567890"
        client = TestClient(api.app)
        headers = {"X-Device-Id": "A" * 43}
        with patch.dict(os.environ, {"API_AUTH_MODE": "required", "API_ACCESS_KEY": secret}, clear=False):
            checks = [
                ("get", "/v1/ai/kumo/status"),
                ("get", "/v1/parmar/strategies"),
                ("get", "/v1/market/candles"),
                ("post", "/v1/smc/analyze"),
                ("get", "/snapshot?symbol=NIFTY&tf=1m"),
            ]
            for method, path in checks:
                with self.subTest(path=path):
                    response = getattr(client, method)(path, headers=headers, json={} if method == "post" else None) if method == "post" else client.get(path, headers=headers)
                    self.assertEqual(response.status_code, 401, f"{path}: {response.status_code} {response.text}")

    def test_websockets_reject_device_id_without_server_auth(self):
        from starlette.websockets import WebSocketDisconnect

        secret = "test-only-long-random-access-key-1234567890"
        client = TestClient(api.app)
        headers = {"X-Device-Id": "A" * 43}
        with patch.dict(os.environ, {"API_AUTH_MODE": "required", "API_ACCESS_KEY": secret}, clear=False):
            for path in ("/ws?symbol=NIFTY", "/ws/chart?symbol=NIFTY&tf=1m"):
                with self.subTest(path=path):
                    with self.assertRaises(WebSocketDisconnect):
                        with client.websocket_connect(path, headers=headers) as websocket:
                            websocket.receive_json()

    def test_rate_limiter_rejects_requests_over_the_window_and_recovers(self):
        key = ("audit-unit-test", "calendar")
        api._rate_limit_windows.pop(key, None)
        try:
            self.assertEqual(api._consume_rate_limit(key[0], key[1], 2, now=100), (True, 1))
            self.assertEqual(api._consume_rate_limit(key[0], key[1], 2, now=101), (True, 0))
            allowed, retry_after = api._consume_rate_limit(key[0], key[1], 2, now=102)
            self.assertFalse(allowed)
            self.assertGreater(retry_after, 0)
            self.assertEqual(api._consume_rate_limit(key[0], key[1], 2, now=162)[0], True)
        finally:
            api._rate_limit_windows.pop(key, None)

    def test_official_nse_holiday_blocks_normal_session(self):
        status = day_status(date(2026, 10, 20), "NSE_FO")
        self.assertEqual(status["market_status"], "EXCHANGE_HOLIDAY")
        self.assertTrue(status["is_holiday"])
        self.assertFalse(api._is_market_session_open("NIFTY", api.datetime(2026, 10, 20, 10, 0, tzinfo=api.IST)))

    def test_muhurat_day_is_listed_as_special_and_not_normal_session(self):
        status = day_status(date(2026, 11, 8), "NSE_FO")
        self.assertEqual(status["market_status"], "SPECIAL_SESSION")
        self.assertEqual(status["special_session"]["timing_status"], "PENDING_OFFICIAL_TIMINGS")
        self.assertFalse(api._is_market_session_open("NIFTY", api.datetime(2026, 11, 8, 10, 0, tzinfo=api.IST)))

    def test_mcx_calendar_is_explicitly_unverified_instead_of_copying_nse_holidays(self):
        status = day_status(date(2026, 10, 20), "MCX")
        self.assertFalse(status["calendar_verified"])
        self.assertEqual(status["market_status"], "CALENDAR_UNVERIFIED")
        self.assertFalse(status["is_holiday"])

    def test_exchange_holiday_endpoint_exposes_provenance_and_coverage(self):
        client = TestClient(api.app)
        response = client.get("/v1/calendar/holidays?year=2026&segment=NSE_FO", headers={"X-Device-Id": "A" * 43})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["verified"])
        self.assertEqual(body["source_status"], "CHECKED_IN_OFFICIAL_SNAPSHOT")
        self.assertIn("2026-10-20", {row["date"] for row in body["holidays"]})

    def test_expired_option_becomes_unresolved_not_a_fabricated_win_or_loss(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signal_outcomes.json"
            path.write_text(json.dumps([{
                "outcome_id": "expired-row",
                "signature": "expired-signature",
                "signal_type": "INDEX_OPTION",
                "index": "NIFTY",
                "decision": "CALL BUY",
                "option_type": "CALL",
                "strike": 25000,
                "expiry": "2020-01-01",
                "entry_price": 100.0,
                "stop_loss": 90.0,
                "target": 120.0,
                "status": "OPEN",
                "opened_at": "2020-01-01T09:20:00+05:30",
                "exit_price": None,
            }]), encoding="utf-8")
            api._signal_outcomes_memory.clear()
            with patch.dict(os.environ, {"SIGNAL_OUTCOMES_FILE": str(path)}, clear=False), \
                 patch.object(api, "get_state", return_value=(False, None)), \
                 patch.object(api, "put_state", return_value=False):
                report = api._update_signal_outcomes({}, {}, [])
                rows = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(rows[0]["status"], "EXPIRED_UNRESOLVED")
            self.assertIsNone(rows[0]["exit_price"])
            self.assertEqual(rows[0]["pnl_status"], "UNRESOLVED_NO_SETTLEMENT_EVIDENCE")
            self.assertEqual(report["expired_unresolved_count"], 1)
            self.assertEqual(report["metrics"]["closed_count"], 0)

    def test_event_journal_records_quant_and_strategy_transitions_without_polling_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "signal_events.json"
            signal = {
                "decision": "WAIT",
                "data_fresh": False,
                "live_validation": {"verdict": "BLOCKED"},
                "signal_stability": {"state": "BLOCKED"},
                "reasons": ["STALE_MARKET_DATA"],
                "layers": {"data_quality": {"pass": False}, "risk_levels": {"pass": False}},
                "strategy_candidates": [{
                    "strategy_id": "vwap_session",
                    "candidate_decision": "WAIT",
                    "state": "BLOCKED",
                    "reasons": ["STALE_MARKET_DATA"],
                }],
            }
            api._signal_events_memory.clear()
            with patch.dict(os.environ, {"SIGNAL_EVENTS_FILE": str(path)}, clear=False), \
                 patch.object(api, "get_state", return_value=(False, None)), \
                 patch.object(api, "put_state", return_value=False):
                first = api._record_signal_events({"NIFTY": signal}, {"NIFTY": {"timestamp": "2026-10-17T09:30:00+05:30"}})
                repeated = api._record_signal_events({"NIFTY": signal}, {"NIFTY": {"timestamp": "2026-10-17T09:30:30+05:30"}})
                changed = dict(signal)
                changed["decision"] = "CALL BUY"
                changed["data_fresh"] = True
                changed["live_validation"] = {"verdict": "PASS"}
                changed["signal_stability"] = {"state": "CONFIRMED"}
                changed["layers"] = {"data_quality": {"pass": True}, "risk_levels": {"pass": True}}
                changed["strategy_candidates"] = [{
                    "strategy_id": "vwap_session", "candidate_decision": "CALL BUY",
                    "state": "CANDIDATE", "reasons": ["VOLUME_CONFIRMED"],
                }]
                third = api._record_signal_events({"NIFTY": changed}, {"NIFTY": {"timestamp": "2026-10-17T09:31:00+05:30"}})
                rows = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(first["new_events"], 2)
            self.assertEqual(repeated["new_events"], 0)
            self.assertEqual(third["new_events"], 2)
            self.assertEqual(len(rows), 4)
            self.assertEqual({row["engine_id"] for row in rows}, {"quant_five_layer", "strategy_candidate"})
            self.assertTrue(all(row["signal_id"] and row["event_id"] for row in rows))
            self.assertTrue(all(row["paper_only"] is True for row in rows))

    def test_date_parser_supports_official_nse_calendar_format(self):
        self.assertEqual(_parse_date_cell("20-Oct-2026"), "2026-10-20")
        self.assertEqual(_parse_date_cell("08-Nov-26"), "2026-11-08")


if __name__ == "__main__":
    unittest.main()
