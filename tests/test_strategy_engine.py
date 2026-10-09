from strategy_engine import evaluate_confluence


def test_missing_evidence_never_fabricates_alignment_score():
    result = evaluate_confluence("WAIT")
    assert result["candidate"] == "WAIT"
    assert result["alignment_score"] is None
    assert result["checks"]["ema_trend"] == "UNKNOWN"


def test_bullish_confluence_is_explained():
    result = evaluate_confluence(
        "CALL BUY",
        ema_fast=105,
        ema_slow=100,
        macd_hist=1.2,
        rsi14=62,
        timeframe_closes={"1m": [100, 101, 102], "5m": [98, 99, 101]},
        option_bid=99.9,
        option_ask=100.1,
        option_ltp=100,
        call_oi_change=1200,
        put_oi_change=300,
    )
    assert result["checks"]["ema_trend"] == "BULLISH"
    assert result["checks"]["multi_timeframe"] == "ALIGNED"
    assert result["alignment_score"] is not None
    assert "not a probability" in result["score_semantics"]


def test_timeframe_conflict_is_visible():
    result = evaluate_confluence(
        "CALL BUY",
        timeframe_closes={"1m": [100, 101, 102], "15m": [102, 101, 100]},
    )
    assert result["checks"]["multi_timeframe"] == "CONFLICT"
