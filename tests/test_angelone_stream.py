import unittest
from datetime import datetime, timezone

from integrations.angelone_stream import AngelOneStream


class FakeAdapter:
    def websocket_credentials(self):
        return {
            "api_key": "test-api-key",
            "client_code": "test-client",
            "jwt_token": "test-jwt",
            "feed_token": "test-feed",
        }


class AngelOneStreamTests(unittest.TestCase):
    def test_normalizes_tick_prices_depth_and_timestamp(self):
        stream = AngelOneStream(FakeAdapter())
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        stream._on_data(None, {
            "token": "99926000",
            "last_traded_price": 2210050,
            "exchange_timestamp": now_ms,
            "volume_trade_for_the_day": 100000,
            "best_5_buy_data": [{"price": 2210000, "quantity": 30, "orders": 2}],
            "best_5_sell_data": [{"price": 2210100, "quantity": 25, "orders": 3}],
        })
        tick = stream.get_tick("99926000")
        self.assertIsNotNone(tick)
        self.assertEqual(tick["ltp"], 22100.5)
        self.assertEqual(tick["best5Data"]["buy"][0]["price"], 22100.0)
        self.assertEqual(tick["best5Data"]["sell"][0]["price"], 22101.0)
        self.assertEqual(tick["_source_mode"], "WEBSOCKET_V2")
        self.assertEqual(stream.status()["tick_count"], 1)
        self.assertEqual(stream.status()["unique_tokens_seen"], 1)

    def test_rejects_ticks_without_token_or_stale_timestamp(self):
        stream = AngelOneStream(FakeAdapter())
        stream._on_data(None, {"last_traded_price": 2210050})
        self.assertEqual(stream.status()["tick_count"], 0)
        stream._on_data(None, {
            "token": "99926000",
            "last_traded_price": 2210050,
            "exchange_timestamp": 1,
        })
        self.assertIsNone(stream.get_tick("99926000"))


if __name__ == "__main__":
    unittest.main()
