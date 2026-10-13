import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.app.main import _aggregate_hourly_chart_rows, _aggregate_weekly_chart_rows

IST = ZoneInfo("Asia/Kolkata")


class ChartTimeframeTests(unittest.TestCase):
    def test_hourly_aggregation_requires_a_complete_same_session_hour(self):
        start = datetime(2026, 10, 12, 9, 15, tzinfo=IST)
        rows = []
        for index in range(12):
            stamp = start + timedelta(minutes=5 * index)
            close = 100.0 + index
            rows.append({
                "t": int(stamp.timestamp()),
                "timestamp": stamp.isoformat(),
                "open": close - 0.5,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 10,
            })
        result = _aggregate_hourly_chart_rows(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["open"], 99.5)
        self.assertEqual(result[0]["high"], 112.0)
        self.assertEqual(result[0]["low"], 99.0)
        self.assertEqual(result[0]["close"], 111.0)
        self.assertEqual(result[0]["volume"], 120)

    def test_hourly_aggregation_never_bridges_overnight_gaps(self):
        rows = []
        for day in (12, 13):
            start = datetime(2026, 10, day, 15, 0, tzinfo=IST)
            for index in range(6):
                stamp = start + timedelta(minutes=5 * index)
                rows.append({
                    "t": int(stamp.timestamp()), "timestamp": stamp.isoformat(),
                    "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1,
                })
        self.assertEqual(_aggregate_hourly_chart_rows(rows), [])

    def test_weekly_aggregation_uses_real_daily_bars(self):
        rows = []
        for day, opened, high, low, close, volume in (
            (12, 100.0, 103.0, 99.0, 102.0, 1000),
            (13, 102.0, 105.0, 101.0, 104.0, 1500),
        ):
            stamp = datetime(2026, 10, day, 15, 30, tzinfo=IST)
            rows.append({
                "t": int(stamp.timestamp()), "timestamp": stamp.isoformat(),
                "open": opened, "high": high, "low": low, "close": close, "volume": volume,
            })
        result = _aggregate_weekly_chart_rows(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["open"], 100.0)
        self.assertEqual(result[0]["high"], 105.0)
        self.assertEqual(result[0]["low"], 99.0)
        self.assertEqual(result[0]["close"], 104.0)
        self.assertEqual(result[0]["volume"], 2500)


if __name__ == "__main__":
    unittest.main()
