from __future__ import annotations
import os
from datetime import date
from typing import Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from .advisor import MultiLevelAdvisor
from .memory import Memory
from .risk import DailyRiskManager
from .broker_angel import AngelReadOnlyBroker

app = FastAPI(title='AI-TRADING Signal-Only Bot', version='0.1.0', description='Paper/advisory scaffold. No broker orders are supported.')
DB_PATH = os.getenv('TRADING_BOT_DB', 'trading_bot_memory.sqlite')
CAPITAL = float(os.getenv('TRADING_BOT_CAPITAL', '100000'))
memory = Memory(DB_PATH)
advisor = MultiLevelAdvisor()
risk = DailyRiskManager(starting_capital=CAPITAL, profit_lock_pct=15, max_loss_pct=5, max_trades=10)
angel_broker = None

class EvaluateRequest(BaseModel):
    candles: list[dict[str, Any]] = Field(min_length=1, max_length=2000)
    spot: float | None = Field(default=None, gt=0)

@app.get('/')
def root():
    return {'service': 'AI-TRADING Signal-Only Bot', 'mode': 'advisory_only', 'orders_enabled': False,
            'endpoints': ['/health', '/status', '/evaluate', '/risk', '/trades', '/daily']}

@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'signal-only-advisor', 'orders_enabled': False}

@app.get('/status')
def status():
    return {'running': True, 'mode': 'advisory_only', 'orders_enabled': False, 'risk': risk.as_dict()}

@app.post('/evaluate')
def evaluate(request: EvaluateRequest):
    try:
        result = advisor.evaluate(request.candles, request.spot, risk.can_open())
        result['as_of'] = request.candles[-1].get('ts') or request.candles[-1].get('timestamp')
        memory.save_evaluation(result)
        return result
    except Exception as exc:
        # Invalid inputs or model failures never fall back to a BUY/SELL signal.
        raise HTTPException(status_code=422, detail=f'Evaluation failed closed: {type(exc).__name__}') from exc

@app.get('/angel/evaluate')
def angel_evaluate():
    """Fetch fresh historical candles from Angel One, then return an advisory only."""
    global angel_broker
    token = os.getenv('ANGEL_SYMBOL_TOKEN', '')
    exchange = os.getenv('ANGEL_EXCHANGE', 'NSE')
    interval = os.getenv('ANGEL_INTERVAL', 'FIVE_MINUTE')
    if not token:
        raise HTTPException(status_code=503, detail='ANGEL_SYMBOL_TOKEN is not configured on the backend')
    try:
        if angel_broker is None:
            angel_broker = AngelReadOnlyBroker.from_env()
        candles = angel_broker.fetch_candles(exchange, token, interval, int(os.getenv('ANGEL_LOOKBACK_DAYS', '5')))
        spot = None
        symbol = os.getenv('ANGEL_TRADING_SYMBOL', '')
        if symbol:
            spot = angel_broker.fetch_ltp(exchange, symbol, token)
        result = advisor.evaluate(candles, spot, risk.can_open())
        result['as_of'] = candles[-1].get('ts') if candles else None
        result['data_source'] = 'angel_one_historical_candles'
        result['orders_sent'] = False
        memory.save_evaluation(result)
        return result
    except Exception as exc:
        # Do not substitute cached candles or return a stale BUY/SELL signal.
        raise HTTPException(status_code=503, detail=f'Angel data unavailable; WAIT: {type(exc).__name__}') from exc

@app.get('/risk')
def risk_status():
    return risk.as_dict()

@app.get('/trades')
def trades(limit: int = 100):
    # This endpoint is intentionally an evaluation log, not a broker tradebook.
    return memory.recent_evaluations(limit)

@app.get('/daily')
def daily(limit: int = 30):
    return memory.recent_daily_metrics(limit)

@app.post('/risk/reset-paper-day')
def reset_paper_day():
    # Explicitly only resets in-memory simulation state; not connected to a broker account.
    global risk
    risk = DailyRiskManager(starting_capital=CAPITAL, profit_lock_pct=15, max_loss_pct=5, max_trades=10)
    snapshot = {'date': date.today().isoformat(), **risk.as_dict(), 'note': 'paper/advisory state only'}
    memory.save_daily_metrics(snapshot['date'], snapshot)
    return snapshot
