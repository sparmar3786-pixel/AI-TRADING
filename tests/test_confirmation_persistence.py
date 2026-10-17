"""Regression tests for durable, server-owned signal confirmation state."""
from unittest.mock import patch

from backend.app import main


def test_confirmation_state_loads_only_from_durable_store():
    with patch.object(main, "get_state", return_value=(True, {"candidate_key": "NIFTY|orb|CALL"})):
        assert main._load_persistent_confirmation_state("NIFTY") == {
            "candidate_key": "NIFTY|orb|CALL"
        }


def test_confirmation_state_does_not_fall_back_to_process_memory_when_store_unavailable():
    main._confirmation_states["NIFTY"] = {"candidate_key": "old-memory-only"}
    with patch.object(main, "get_state", return_value=(False, None)):
        assert main._load_persistent_confirmation_state("NIFTY") is None


def test_confirmation_state_save_reports_durable_write_failure():
    with patch.object(main, "put_state", return_value=False) as save:
        assert main._save_persistent_confirmation_state("NIFTY", {"elapsed_seconds": 300}) is False
        save.assert_called_once_with("signal_confirmation:NIFTY", {"elapsed_seconds": 300})


def test_confirmation_state_save_reports_durable_write_success():
    with patch.object(main, "put_state", return_value=True):
        assert main._save_persistent_confirmation_state("NIFTY", {"elapsed_seconds": 300}) is True
