import { IndexSymbol, MarketRow, SignalData } from '../types/market';
import { nvidiaService } from './nvidiaService';
import { apiService } from './api';

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
1. Provide concise, highly actionable, institutional-grade quant analysis in professional, helpful tone (English / clear Hinglish if appropriate).
2. Reference exact support & resistance levels, strike selection, and Greeks.
3. Always emphasize risk management and stop-loss discipline.
4. Format with clean bullet points and bold highlights.`;

  // 1. Check if user has configured NVIDIA NIM API Key or preferred provider
  if (nvidiaService.isNvidiaConfigured()) {
    try {
      const nvidiaResult = await nvidiaService.queryNvidiaNim(
        question,
        systemPrompt,
        history
      );
      if (nvidiaResult && nvidiaResult.answer.trim().length > 0) {
        return {
          answer: nvidiaResult.answer,
          provider: 'NVIDIA NIM',
          model: nvidiaResult.model,
        };
      }
    } catch (e) {
      console.warn('Direct NVIDIA NIM call failed; trying the server-side cloud provider:', e);
    }
  }

  // 2. Try Railway Backend NVIDIA Cloud endpoint
  try {
    const backendUrl = apiService.getSignalBackend().replace(/\/+$/, '');
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 20000);

    const resp = await fetch(`${backendUrl}/v1/ai/nvidia-chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Device-Id': apiService.getDeviceId(),
        Accept: 'application/json',
      },
      body: JSON.stringify({
        index,
        question,
        history: history.slice(-4),
      }),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (resp.ok) {
      const body = await resp.json();
      const ans = typeof body?.answer === 'string' ? body.answer.trim() : '';
      // Ensure answer is not an error message about rate limits or missing data
      const actualProvider = String(body.provider || '').toLowerCase();
      const isRealCloudInference = body.llm_used !== false &&
        actualProvider !== 'deterministic_fallback' &&
        actualProvider !== 'none' &&
        Boolean(body.model);
      if (ans && isRealCloudInference &&
          !ans.toLowerCase().includes('cannot be determined due to unavailable')) {
        return {
          answer: ans,
          provider: body.provider || 'NVIDIA NIM (Cloud AI)',
          model: body.model,
        };
      }
    }
  } catch (_) {
    // Backend offline or timeout
  }

  // No Gemini or template-based "AI" fallback: report provider failure truthfully.
  // The built-in deterministic quant engine remains authoritative for gates/signals,
  // but it must not impersonate an NVIDIA/Cloud LLM answer.
  throw new Error(
    'Cloud AI unavailable: NVIDIA inference did not return a real response. ' +
    'Check Railway /v1/ai/status and run the AI provider test; OpenRouter is the configured fallback.'
  );
}
