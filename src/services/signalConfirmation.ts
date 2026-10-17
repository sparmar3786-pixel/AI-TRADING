/**
 * Client-side fail-closed guard for the external backend's server-owned signal contract.
 *
 * This module does not calculate or start a 600-second timer. It only accepts an
 * already-confirmed backend decision when the response carries fresh, consistent
 * evidence for the market session, five Quant layers, selected option contract,
 * risk levels, and server confirmation.
 */
type JsonMap = Record<string, unknown>;

const BUY_DECISIONS = new Set(['CALL BUY', 'PUT BUY']);
const REQUIRED_LAYERS = [
  'data_quality',
  'trend_sentiment',
  'order_flow',
  'option_selection',
  'risk_levels',
] as const;
const FRESHNESS_MS = 120_000;
const REQUIRED_STABILITY_SECONDS = 600;

function mapOf(value: unknown): JsonMap {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as JsonMap
    : {};
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function positive(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0;
}

function freshTimestamp(value: unknown, now: number): boolean {
  const timestamp = typeof value === 'string' ? Date.parse(value) : NaN;
  const age = now - timestamp;
  return Number.isFinite(timestamp) && age >= 0 && age <= FRESHNESS_MS;
}

function sameText(left: unknown, right: unknown): boolean {
  return typeof left === 'string' && left.length > 0 && left === right;
}

function isTrustedMarketSession(sessionValue: unknown, now: number): boolean {
  const session = mapOf(sessionValue);
  return session.authority === 'exchange-calendar' &&
    (session.exchange === 'NSE' || session.exchange === 'BSE') &&
    session.is_open === true &&
    session.is_holiday === false &&
    (session.session_type === 'REGULAR' || session.session_type === 'SPECIAL') &&
    text(session.session_id).length > 0 &&
    freshTimestamp(session.checked_at_utc, now);
}

function hasFiveLayerEvidence(engineValue: unknown, now: number): boolean {
  const engine = mapOf(engineValue);
  if (engine.data_fresh !== true || !freshTimestamp(engine.timestamp, now)) return false;
  const layers = mapOf(engine.layers);
  const keys = Object.keys(layers);
  if (keys.length !== REQUIRED_LAYERS.length ||
      REQUIRED_LAYERS.some((key) => !Object.prototype.hasOwnProperty.call(layers, key))) {
    return false;
  }
  return REQUIRED_LAYERS.every((key) => {
    const layer = mapOf(layers[key]);
    return text(layer.status).toUpperCase() === 'PASS' &&
      text(layer.detail ?? layer.reason ?? layer.message).length > 0 &&
      freshTimestamp(layer.timestamp, now) &&
      Object.keys(mapOf(layer.input_provenance)).length > 0;
  });
}

function hasServerConfirmation(signal: JsonMap, engineValue: unknown, now: number): boolean {
  const root = mapOf(signal.signal_stability);
  const engine = mapOf(engineValue);
  const nested = mapOf(engine.confirmation);
  const candidateId = text(signal.candidate_id);
  const rootRequired = root.required_seconds;
  const nestedRequired = nested.required_seconds;
  const rootElapsed = root.elapsed_seconds;
  const nestedElapsed = nested.elapsed_seconds;
  return root.state === 'CONFIRMED' &&
    nested.state === 'CONFIRMED' &&
    root.server_confirmed === true &&
    nested.server_confirmed === true &&
    positive(rootRequired) && rootRequired >= REQUIRED_STABILITY_SECONDS &&
    positive(nestedRequired) && nestedRequired >= REQUIRED_STABILITY_SECONDS &&
    rootRequired === nestedRequired &&
    positive(rootElapsed) && rootElapsed >= REQUIRED_STABILITY_SECONDS &&
    positive(nestedElapsed) && nestedElapsed >= REQUIRED_STABILITY_SECONDS &&
    rootElapsed === nestedElapsed &&
    candidateId.length > 0 &&
    sameText(root.candidate_id, candidateId) &&
    sameText(nested.candidate_id, candidateId) &&
    freshTimestamp(root.confirmed_at_utc, now) &&
    sameText(root.confirmed_at_utc, nested.confirmed_at_utc);
}

function contractExpiryIsValid(signal: JsonMap, contract: JsonMap, now: number): boolean {
  const expiry = text(signal.expiry);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(expiry) || expiry !== text(contract.expiry)) return false;
  const expiryMs = Date.parse(expiry + 'T00:00:00Z');
  if (!Number.isFinite(expiryMs) || new Date(expiryMs).toISOString().slice(0, 10) !== expiry) return false;
  const istDate = new Date(now + 5.5 * 60 * 60 * 1000).toISOString().slice(0, 10);
  return expiry >= istDate;
}

export function isServerConfirmedSignal(
  signalValue: unknown,
  marketSession: unknown,
  now = Date.now(),
): boolean {
  const signal = mapOf(signalValue);
  const decision = text(signal.decision).toUpperCase();
  if (!BUY_DECISIONS.has(decision) ||
      signal.data_fresh !== true ||
      !freshTimestamp(signal.timestamp, now) ||
      signal.price_basis !== 'OPTION_PREMIUM') return false;

  const expectedSide = decision === 'CALL BUY' ? 'CE' : 'PE';
  if (signal.option_side !== expectedSide) return false;
  if (!isTrustedMarketSession(marketSession, now)) return false;

  const validation = mapOf(signal.live_validation);
  if (text(validation.verdict).toUpperCase() !== 'PASS' ||
      text(validation.decision).toUpperCase() !== decision ||
      !Array.isArray(validation.blocks) ||
      validation.blocks.length !== 0 ||
      !Array.isArray(signal.guards) ||
      signal.guards.length !== 0) return false;

  const strike = signal.strike;
  const entry = signal.entry;
  const stopLoss = signal.stop_loss;
  const target = signal.target;
  if (!positive(strike) || !positive(entry) || !positive(stopLoss) ||
      !positive(target) || !(stopLoss < entry && entry < target)) return false;

  const contract = mapOf(signal.option_contract);
  if (!text(contract.symbol) ||
      !text(contract.instrument_token) ||
      contract.option_side !== expectedSide ||
      !positive(contract.premium) ||
      !freshTimestamp(contract.quote_timestamp, now) ||
      !contractExpiryIsValid(signal, contract, now)) return false;
  const premiumTolerance = Math.max(0.05, entry * 0.01);
  if (Math.abs(contract.premium - entry) > premiumTolerance) return false;

  const engineValue = signal.quant_engine ?? signal.five_layer_engine;
  if (!hasFiveLayerEvidence(engineValue, now) ||
      !hasServerConfirmation(signal, engineValue, now)) return false;

  return true;
}

function blockBuy(signalValue: unknown, blocker: string): JsonMap {
  const signal = { ...mapOf(signalValue) };
  const currentDecision = text(signal.decision).toUpperCase();
  const candidateDecision = BUY_DECISIONS.has(currentDecision)
    ? currentDecision
    : text(signal.candidate_decision);
  if (BUY_DECISIONS.has(candidateDecision)) signal.candidate_decision = candidateDecision;
  signal.decision = 'WAIT';
  signal.signal_stability = {
    state: 'NOT_ACTIONABLE',
    required_minutes: 10,
    required_seconds: REQUIRED_STABILITY_SECONDS,
    server_confirmed: false,
  };
  const previousValidation = mapOf(signal.live_validation);
  const oldBlocks = Array.isArray(previousValidation.blocks)
    ? previousValidation.blocks.filter((item): item is string => typeof item === 'string')
    : [];
  signal.live_validation = {
    ...previousValidation,
    verdict: 'WARN',
    decision: 'WAIT',
    blocks: [...new Set([...oldBlocks, blocker])],
  };
  signal.signal_blockers = [...new Set([
    ...(Array.isArray(signal.signal_blockers)
      ? signal.signal_blockers.filter((item): item is string => typeof item === 'string')
      : []),
    blocker,
  ])];
  return signal;
}

/** Suppress any client-visible BUY unless every backend-owned proof is present. */
export function applyServerOwnedSignalGate(
  rawSignalsValue: unknown,
  marketSession: unknown,
  now = Date.now(),
): Record<string, JsonMap> {
  const rawSignals = mapOf(rawSignalsValue);
  const output: Record<string, JsonMap> = {};
  for (const [key, signalValue] of Object.entries(rawSignals)) {
    const signal = mapOf(signalValue);
    const decision = text(signal.decision).toUpperCase();
    const candidate = text(signal.candidate_decision).toUpperCase();
    const hasBuy = BUY_DECISIONS.has(decision) || BUY_DECISIONS.has(candidate);
    const guarded = isServerConfirmedSignal(signal, marketSession, now);
    if (hasBuy && !guarded) {
      output[key] = blockBuy(signal, 'Server-owned session, Quant evidence, option contract or 600-second confirmation is missing, stale, inconsistent, or failed.');
    } else if (guarded) {
      output[key] = { ...signal, server_decision_verified: true };
    } else {
      output[key] = { ...signal, server_decision_verified: false };
    }
  }
  return output;
}
