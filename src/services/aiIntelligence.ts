import { IndexSymbol, MarketRow, SignalData } from '../types/market';
import { nvidiaService } from './nvidiaService';
import { apiService } from './api';
import { stripRepositoryLinks } from './repositoryLinkFilter';

export interface AIResponse {
  answer: string;
  provider: string;
  model: string;
}

/**
 * Universal AI Market Intelligence engine for Indian Equity Indices
 * NVIDIA direct inference -> Railway NVIDIA/OpenRouter inference. Never label a template as cloud AI.
 */
export async function generateMarketIntelligenceAnswer(params: {
  index: IndexSymbol;
  question: string;
  market?: MarketRow;
  signal?: SignalData;
  history?: { role: 'user' | 'assistant'; content: string }[];
}): Promise<AIResponse> {
  const { index, question, market, signal, history = [] } = params;
  const ltp = market?.ltp || 0;
  const change = market?.change || 0;
  const changePct = market?.change_percent || 0;
  const trend = market?.trend || 'NEUTRAL';
  const pcr = market?.pcr;
  const maxPain = market?.max_pain;
  const decision = signal?.decision || 'WAIT';
  const confidence = signal?.confidence;

  const systemPrompt = `You are NVIDIA AI Market Intelligence, an elite algorithmic trading quant analyst and mentor specialized in Indian NSE indices (NIFTY 50, BANKNIFTY, FINNIFTY, SENSEX, MIDCPNIFTY).
Current Market Context:
- Index: ${index}
- Last Traded Price (LTP): ₹${ltp.toLocaleString('en-IN')} (${change >= 0 ? '+' : ''}${change} / ${changePct}%)
- Trend: ${trend}
- Put-Call Ratio (PCR): ${pcr ?? 'unavailable'}
- Max Pain: ${typeof maxPain === 'number' ? `₹${maxPain.toLocaleString('en-IN')}` : 'unavailable'}
- Algo Decision: ${decision} (Confidence: ${typeof confidence === 'number' ? `${confidence}%` : 'unavailable'})
- 10-Minute Stability Gate: ${signal?.signal_stability?.state || 'ACTIVE'}

Instructions:
1. Provide concise, professional analysis in English or clear Hinglish.
2. Use only values explicitly present in the supplied context; if support/resistance, strike, Greeks, or other fields are missing, say unavailable instead of estimating or inventing them.
3. Never turn WAIT into a buy/sell recommendation and never claim a trade is safe or profitable.
4. Emphasize risk management and format with clean bullets.`;

  // NVIDIA is the primary provider and inference runs through Railway so credentials stay server-side.
  // Do not call NVIDIA directly from the browser or silently hide backend errors.
  const backendUrl = apiService.getSignalBackend().replace(/\\/+$/, '');
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 20000);
  let response: Response;
  try {
    response = await fetch(`${backendUrl}/v1/ai/nvidia-chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Device-Id': apiService.getDeviceId(),
        Accept: 'application/json',
      },
      body: JSON.stringify({ index, question, history: history.slice(-4), context: {
        ltp, change, change_percent: changePct, trend, pcr, max_pain: maxPain,
        decision, confidence, signal_stability: signal?.signal_stability?.state || 'ACTIVE',
      } }),
      signal: controller.signal,
      cache: 'no-store',
    });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('NVIDIA Railway inference timed out after 20 seconds.');
    }
    throw new Error(`Cannot reach NVIDIA Railway inference endpoint: ${error instanceof Error ? error.message : 'network/CORS error'}`);
  } finally {
    clearTimeout(timeoutId);
  }

  const raw = await response.text();
  let body: any = {};
  try { body = raw ? JSON.parse(raw) : {}; } catch { body = {}; }
  if (!response.ok) {
    const detail = typeof body.detail === 'string' ? body.detail
      : typeof body.error === 'string' ? body.error
      : raw.slice(0, 240);
    throw new Error(`NVIDIA inference HTTP ${response.status}: ${detail || response.statusText}`);
  }

  const answer = typeof body.answer === 'string' ? body.answer.trim() : '';
  const provider = String(body.provider || '').toLowerCase();
  const realInference = body.llm_used !== false &&
    !['deterministic_fallback', 'none', 'template', 'offline'].includes(provider) &&
    Boolean(body.model);
  if (!answer || !realInference) {
    throw new Error(String(body.error || body.detail ||
      'Railway responded, but did not confirm a real NVIDIA model inference (answer/provider/model missing).'));
  }
  return {
    answer: stripRepositoryLinks(answer),
    provider: String(body.provider || 'NVIDIA NIM'),
    model: String(body.model),
  };
}
