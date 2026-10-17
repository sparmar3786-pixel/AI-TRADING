import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import _cached_signal_source_is_fresh


def _cached(age_seconds=2.0, passed=True):
    return {
        "signals": {
            "NIFTY": {
                "layers": {
                    "data_quality": {
                        "pass": passed,
                        "age_seconds": age_seconds,
                    }
                }
            },
            "BANKNIFTY": {
                "layers": {
                    "data_quality": {
                        "pass": passed,
                        "age_seconds": age_seconds,
                    }
                }
            },
        }
    }


def test_cache_hit_stays_live_only_if_source_and_cache_age_fit_15_seconds():
    assert _cached_signal_source_is_fresh(_cached(age_seconds=3), 5) is True
    assert _cached_signal_source_is_fresh(_cached(age_seconds=11), 5) is False
    assert _cached_signal_source_is_fresh(_cached(age_seconds=2), 13.1) is False


def test_cache_hit_fails_closed_if_any_index_has_bad_or_missing_evidence():
    assert _cached_signal_source_is_fresh(_cached(age_seconds=2, passed=False), 1) is False
    assert _cached_signal_source_is_fresh({}, 1) is False
    assert _cached_signal_source_is_fresh({"signals": {"NIFTY": {}}}, 1) is False


def test_cache_hit_rejects_negative_or_unknown_source_age():
    assert _cached_signal_source_is_fresh(_cached(age_seconds=-1), 1) is False
    assert _cached_signal_source_is_fresh(_cached(age_seconds=None), 1) is False
