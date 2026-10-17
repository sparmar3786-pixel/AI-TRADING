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

  private lastStatus: { configured: boolean; active: boolean; checkedAt: number } | null = null;
  private readonly STATUS_TTL_MS = 30_000;

  public async refreshNvidiaStatus(): Promise<{ configured: boolean; active: boolean }> {
    const { apiService } = await import('./api');
    const backendUrl = apiService.getSignalBackend().replace(/\/+$/, '');
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(`${backendUrl}/v1/system/diagnostics`, {
        headers: await apiService.getAuthHeaders(),
        signal: controller.signal,
        cache: 'no-store',
      });
      if (!response.ok) throw new Error(`Diagnostics HTTP ${response.status}`);
      const data = await response.json();
      const ai = data?.ai_provider ?? {};
      const status = String(ai.nvidia_status ?? '').toLowerCase();
      const configured = Boolean(ai.configured) &&
        !['', 'unavailable', 'not_configured', 'disabled', 'error', 'failed'].includes(status);
      // Diagnostics prove configuration only. Active requires recent successful inference.
      const inferenceStillFresh = Boolean(this.lastStatus?.active &&
        Date.now() - this.lastStatus.checkedAt <= this.STATUS_TTL_MS);
      this.lastStatus = { configured, active: inferenceStillFresh, checkedAt: inferenceStillFresh ? this.lastStatus!.checkedAt : Date.now() };
      return { configured, active: inferenceStillFresh };
    } catch {
      const inferenceStillFresh = Boolean(this.lastStatus?.active &&
        Date.now() - this.lastStatus.checkedAt <= this.STATUS_TTL_MS);
      this.lastStatus = { configured: false, active: inferenceStillFresh, checkedAt: inferenceStillFresh ? this.lastStatus!.checkedAt : Date.now() };
      return { configured: false, active: inferenceStillFresh };
    } finally {
      clearTimeout(timeoutId);
    }
  }

  public isNvidiaConfigured(): boolean {
    return Boolean(this.lastStatus?.configured && Date.now() - this.lastStatus.checkedAt <= this.STATUS_TTL_MS);
  }

  public isNvidiaActive(): boolean {
    return Boolean(this.lastStatus?.active && Date.now() - this.lastStatus.checkedAt <= this.STATUS_TTL_MS);
  }

  /** Record a real chat response without mistaking OpenRouter fallback for NVIDIA inference. */
  public recordInferenceResult(provider: string, model: string): void {
    const isNvidiaInference = /nvidia|nim/i.test(provider);
    this.lastStatus = {
      configured: isNvidiaInference || Boolean(this.lastStatus?.configured),
      active: isNvidiaInference && Boolean(model.trim()),
      checkedAt: Date.now(),
    };
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
    const backendUrl = apiService.getSignalBackend().replace(/\/+$/, '');
    const response = await fetch(`${backendUrl}/v1/ai/nvidia-chat`, {
      method: 'POST',
      headers: {
        ...(await apiService.getAuthHeaders()),
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        index: 'NIFTY',
        question: [systemPrompt, prompt].join(String.fromCharCode(10).repeat(2)),
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
    this.recordInferenceResult(provider, model);
    return { answer, model, provider: provider || 'Unknown provider' };
  }


}

export const nvidiaService = new NvidiaService();
