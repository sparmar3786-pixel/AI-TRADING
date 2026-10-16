import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import main as api


class CompletedSourceCandleTests(unittest.TestCase):
    def test_primary_normalizer_drops_in_progress_future_and_invalid_rows(self):
        now = datetime(2026, 10, 16, 9, 28, tzinfo=timezone.utc)
        source = [
            ["2026-10-16T09:15:00+00:00", 100, 102, 99, 101, 1000],
            ["2026-10-16T09:20:00+00:00", 101, 103, 100, 102, 1200],
            ["2026-10-16T09:25:00+00:00", 102, 104, 101, 103, 1400],
            ["2026-10-16T09:10:00+00:00", 100, 99, 101, 102, 500],
            ["bad", 100, 101, 99, 100, 100],
            ["2026-10-16T09:10:00+00:00", 100, 101],
        ]

        result = api._completed_source_candle_rows(source, now=now)

        self.assertEqual(len(result), 2)
        self.assertEqual([row[4] for row in result], [101, 102])
        self.assertTrue(all(datetime.fromisoformat(row[0]).tzinfo is not None for row in result))

    def test_all_in_progress_candles_produce_no_completed_rows(self):
        now = datetime(2026, 10, 16, 9, 28, tzinfo=timezone.utc)
        source = [
            ["2026-10-16T09:25:00+00:00", 102, 104, 101, 103, 1400],
            ["2026-10-16T09:26:00+00:00", 103, 104, 102, 103.5, 100],
        ]
        self.assertEqual(api._completed_source_candle_rows(source, now=now), [])

    def test_bad_market_values_do_not_enter_indicator_input(self):
        now = datetime(2026, 10, 16, 9, 40, tzinfo=timezone.utc)
        source = [
            ["2026-10-16T09:15:00+00:00", 100, 102, 99, 101, 1000],
            ["2026-10-16T09:20:00+00:00", 101, 103, 100, 102, -1],
            ["2026-10-16T09:25:00+00:00", 0, 103, 100, 102, 500],
            ["2026-10-16T09:30:00+00:00", 102, 104, 101, 103, None],
        ]
        result = api._completed_source_candle_rows(source, now=now)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][4], 101)
        self.assertEqual(result[1][4], 103)
        self.assertIsNone(result[1][5])


if __name__ == "__main__":
    unittest.main()
