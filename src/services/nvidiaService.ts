/**
 * NVIDIA NIM & AI Market Intelligence Service
 * Handles server-side NVIDIA cloud inference and reports verified status only.
 */

export interface NvidiaModelInfo {
  id: string;
  name: string;
  description: string;
  recommended?: boolean;
}

export const SUPPORTED_NVIDIA_MODELS: NvidiaModelInfo[] = [
  {
    id: 'z-ai/glm-5.3',
    name: 'NVIDIA Hosted GLM 5.3',
    description: 'Current server-configured cloud model; inference must return successfully to be shown as connected.',
    recommended: true,
  },
];

export interface MarketArticle {
  index: string;
  title: string;
  url?: string;
  source: string;
  published_at: string;
  sentiment: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  score?: number;
  content: string;
}

const STORAGE_KEY_SELECTED_MODEL = 'ai_trading_nvidia_model';
const STORAGE_KEY_AI_PROVIDER = 'ai_trading_preferred_provider';

class NvidiaService {
  private defaultModel = 'z-ai/glm-5.3';

  // Provider secrets must remain on Railway; never persist them in browser storage.
  public getNvidiaApiKey(): string {
    return '';
  }

  public setNvidiaApiKey(_key: string): void {
    // Intentionally disabled: configure NVIDIA credentials in Railway environment variables.
  }

  public isNvidiaConfigured(): boolean {
    return false; // Configuration is verified by server status/inference, not browser-held keys.
  }

  public isNvidiaActive(): boolean {
    return false; // Do not mark active until a real backend inference has succeeded.
  }

  public getEngineStatusLabel(): { label: string; isDirectKey: boolean } {
    return { label: 'NVIDIA STATUS REQUIRES RAILWAY VERIFICATION', isDirectKey: false };
  }

  public getSelectedModel(): string {
    const saved = localStorage.getItem(STORAGE_KEY_SELECTED_MODEL);
    // Migrate stale model IDs to the model configured by the server.
    return SUPPORTED_NVIDIA_MODELS.some(model => model.id === saved) ? saved! : this.defaultModel;
  }

  public setSelectedModel(model: string): void {
    localStorage.setItem(STORAGE_KEY_SELECTED_MODEL, model);
  }

  public getPreferredProvider(): 'nvidia' | 'quant' {
    const saved = localStorage.getItem(STORAGE_KEY_AI_PROVIDER);
    if (saved === 'nvidia' || saved === 'quant') {
      return saved;
    }
    return 'nvidia';
  }

  public setPreferredProvider(provider: 'nvidia' | 'quant'): void {
    localStorage.setItem(STORAGE_KEY_AI_PROVIDER, provider);
  }

  /**
   * Never test or send user-supplied keys from the browser. Keys are server-side only.
   */
  public async validateNvidiaKey(_apiKey: string): Promise<{ valid: boolean; message: string }> {
    return {
      valid: false,
      message: 'Browser key entry is disabled. Configure NVIDIA_API_KEY on Railway and verify using a real backend inference.',
    };
  }

  /**
   * NVIDIA cloud inference through Railway only. No provider key is read by this client.
   */
  public async queryNvidiaNim(
    prompt: string,
    systemPrompt: string,
    history: { role: 'user' | 'assistant'; content: string }[] = [],
    modelOverride?: string
  ): Promise<{ answer: string; model: string; provider: string } | null> {
    const { apiService } = await import('./api');
    const backendUrl = apiService.getSignalBackend().replace(/\\/+$/, '');
    const response = await fetch(`${backendUrl}/v1/ai/nvidia-chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Device-Id': apiService.getDeviceId(),
        Accept: 'application/json',
      },
      body: JSON.stringify({
        index: 'NIFTY',
        question: `${systemPrompt}\\n\\n${prompt}`,
        history: history.slice(-4),
        context: { requested_model: modelOverride || this.getSelectedModel() },
      }),
      cache: 'no-store',
    });
    const raw = await response.text();
    let data: any = {};
    try { data = raw ? JSON.parse(raw) : {}; } catch { /* handled below */ }
    if (!response.ok) {
      throw new Error(`NVIDIA Railway inference HTTP ${response.status}: ${String(data.detail || data.error || raw).slice(0, 240)}`);
    }
    const answer = typeof data.answer === 'string' ? data.answer.trim() : '';
    const provider = String(data.provider || '');
    const model = String(data.model || '');
    if (!answer || !model || data.llm_used === false ||
        ['deterministic_fallback', 'none', 'template', 'offline'].includes(provider.toLowerCase())) {
      throw new Error('Backend did not confirm a real NVIDIA model inference.');
    }
    return { answer, model, provider: provider || 'NVIDIA NIM' };
  }


}

export const nvidiaService = new NvidiaService();
