import test from 'node:test';
import assert from 'node:assert/strict';
import { applyServerOwnedSignalGate } from '../src/services/signalConfirmation.ts';

const NOW = Date.parse('2026-10-19T10:00:00+05:30');
const recent = new Date(NOW - 15_000).toISOString();
const candidateId = 'NIFTY-CALL-20261029-25000-001';

function fixture() {
  const layers = {
    data_quality: { status: 'PASS', detail: 'Fresh Angel One quote', timestamp: recent, input_provenance: { source: 'ANGEL_ONE', field: 'ltp' } },
    trend_sentiment: { status: 'PASS', detail: 'Trend aligned', timestamp: recent, input_provenance: { source: 'CANDLES', field: 'close' } },
    order_flow: { status: 'PASS', detail: 'Bid/ask pressure valid', timestamp: recent, input_provenance: { source: 'ANGEL_ONE', field: 'depth' } },
    option_selection: { status: 'PASS', detail: 'Liquid contract selected', timestamp: recent, input_provenance: { source: 'ANGEL_ONE', field: 'option_chain' } },
    risk_levels: { status: 'PASS', detail: 'Premium risk levels valid', timestamp: recent, input_provenance: { source: 'RISK_ENGINE', field: 'risk_levels' } },
  };
  const confirmation = {
    state: 'CONFIRMED', server_confirmed: true, required_seconds: 600,
    elapsed_seconds: 615, candidate_id: candidateId, confirmed_at_utc: recent,
  };
  return {
    market_session: {
      authority: 'exchange-calendar', exchange: 'NSE', is_open: true,
      is_holiday: false, session_type: 'REGULAR', special_session: false,
      session_id: 'NSE:2026-10-19:REGULAR', checked_at_utc: recent,
    },
    signals: {
      NIFTY: {
        index: 'NIFTY', decision: 'CALL BUY', candidate_decision: 'CALL BUY',
        candidate_id: candidateId, timestamp: recent, data_fresh: true,
        strike: 25000, option_side: 'CE', price_basis: 'OPTION_PREMIUM',
        entry: 120, stop_loss: 110, target: 140, expiry: '2026-10-29',
        option_contract: {
          symbol: 'NIFTY29OCT2625000CE', instrument_token: '12345',
          option_side: 'CE', expiry: '2026-10-29', premium: 120,
          quote_timestamp: recent,
        },
        guards: [],
        live_validation: { verdict: 'PASS', decision: 'CALL BUY', blocks: [] },
        quant_engine: { data_fresh: true, timestamp: recent, layers, confirmation },
        signal_stability: { ...confirmation, required_minutes: 10 },
      },
    },
    trade_plans: [{ index: 'NIFTY', candidate_id: candidateId }],
    qualified_trade_count: 1,
  };
}

test('client-side or local-storage timing cannot confirm a BUY without server-owned evidence', () => {
  const payload = fixture();
  const signal = payload.signals.NIFTY;
  delete signal.signal_stability.server_confirmed;
  delete signal.quant_engine.confirmation.server_confirmed;
  delete signal.signal_stability.candidate_id;
  delete signal.quant_engine.confirmation.candidate_id;

  const gated = applyServerOwnedSignalGate(payload.signals, payload.market_session, NOW);
  assert.equal(gated.NIFTY.decision, 'WAIT');
  assert.equal(gated.NIFTY.signal_stability.server_confirmed, false);
});

test('a complete fresh backend confirmation with five evidence-backed layers passes', () => {
  const payload = fixture();
  const gated = applyServerOwnedSignalGate(payload.signals, payload.market_session, NOW);
  assert.equal(gated.NIFTY.decision, 'CALL BUY');
  assert.equal(gated.NIFTY.signal_stability.server_confirmed, true);
});

test('a holiday or closed authoritative exchange session blocks a BUY', () => {
  const payload = fixture();
  payload.market_session.is_open = false;
  payload.market_session.is_holiday = true;
  const gated = applyServerOwnedSignalGate(payload.signals, payload.market_session, NOW);
  assert.equal(gated.NIFTY.decision, 'WAIT');
});

test('missing layer provenance blocks a BUY even when all layer statuses say PASS', () => {
  const payload = fixture();
  delete payload.signals.NIFTY.quant_engine.layers.order_flow.input_provenance;
  const gated = applyServerOwnedSignalGate(payload.signals, payload.market_session, NOW);
  assert.equal(gated.NIFTY.decision, 'WAIT');
});

test('option premium mismatch and expired contracts block a BUY', () => {
  const mismatched = fixture();
  mismatched.signals.NIFTY.entry = 150;
  assert.equal(applyServerOwnedSignalGate(mismatched.signals, mismatched.market_session, NOW).NIFTY.decision, 'WAIT');

  const expired = fixture();
  expired.signals.NIFTY.option_contract.expiry = '2026-10-18';
  expired.signals.NIFTY.expiry = '2026-10-18';
  assert.equal(applyServerOwnedSignalGate(expired.signals, expired.market_session, NOW).NIFTY.decision, 'WAIT');
});

test('bad stop-loss / target ordering blocks a BUY', () => {
  const payload = fixture();
  payload.signals.NIFTY.stop_loss = 121;
  assert.equal(applyServerOwnedSignalGate(payload.signals, payload.market_session, NOW).NIFTY.decision, 'WAIT');
});
