"""Smoke tests for the deployable read-only AI-TRADING API."""
import unittest

from backend.app.main import app, health


class BackendApiSmokeTests(unittest.TestCase):
    def test_health_is_dependency_free_and_reports_service(self):
        result = health()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["service"], "ai-trading-readonly-api")
        self.assertIn("time", result)

    def test_openapi_exposes_signal_and_broker_read_routes(self):
        paths = app.openapi()["paths"]
        for path in (
            "/health",
            "/v1/metadata",
            "/v1/angel/status",
            "/v1/angel/connect",
            "/v1/option-chain",
            "/v1/signals",
            "/v1/backtest/historical",
            "/v1/live/status",
        ):
            self.assertIn(path, paths, f"Expected API route missing: {path}")

    def test_api_does_not_expose_order_placement_route(self):
        for path, operations in app.openapi()["paths"].items():
            if any(term in path.lower() for term in ("place-order", "execute-order", "order-placement")):
                self.fail(f"Order-placement path must not be exposed by signal-only API: {path}")
            for method in operations:
                if method.lower() == "post" and "order" in path.lower():
                    self.fail(f"POST order route must not be exposed by signal-only API: {path}")


if __name__ == "__main__":
    unittest.main()
