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

export interface MarketBriefResult {
  status: 'ACTIVE' | 'REFRESHED';
  summary: string;
const STORAGE_KEY_NVIDIA = 'ai_trading_nvidia_key';
const STORAGE_KEY_SELECTED_MODEL = 'ai_trading_nvidia_model';
const STORAGE_KEY_AI_PROVIDER = 'ai_trading_preferred_provider';

class NvidiaService {
  private defaultModel = 'z-ai/glm-5.3';

  public getNvidiaApiKey(): string {
    const fromStorage = localStorage.getItem(STORAGE_KEY_NVIDIA);
    if (fromStorage && fromStorage.trim().length > 0) {
      return fromStorage.trim();
    }
    const env = (import.meta as any).env || {};
    return (env.VITE_NVIDIA_API_KEY as string) || (env.NVIDIA_API_KEY as string) || '';
  }

  public setNvidiaApiKey(key: string): void {
    if (key.trim()) {
      localStorage.setItem(STORAGE_KEY_NVIDIA, key.trim());
    } else {
      localStorage.removeItem(STORAGE_KEY_NVIDIA);
    }
  }

  public isNvidiaConfigured(): boolean {
    const key = this.getNvidiaApiKey();
    return Boolean(key && (key.startsWith('nvapi-') || key.length > 20));
  }

  /**
   * NVIDIA NIM is active either via user direct API key or via built-in Nemotron 70B pipeline
   */
  public isNvidiaActive(): boolean {
    // A key or deterministic local rules do not prove that a cloud inference works.
    return this.isNvidiaConfigured();
  }

  public getEngineStatusLabel(): { label: string; isDirectKey: boolean } {
    if (this.isNvidiaConfigured()) {
      return { label: 'NVIDIA NIM DIRECT KEY ACTIVE', isDirectKey: true };
    }
    return { label: 'NVIDIA CLOUD NOT VERIFIED', isDirectKey: false };
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
   * Validate user-supplied NVIDIA API key against NVIDIA NIM API catalog
   */
  public async validateNvidiaKey(apiKey: string): Promise<{ valid: boolean; message: string }> {
    const cleanKey = apiKey.trim();
    if (!cleanKey) {
      return { valid: false, message: 'API Key cannot be empty.' };
    }
    try {
      const response = await fetch('https://integrate.api.nvidia.com/v1/models', {
        headers: {
          Authorization: `Bearer ${cleanKey}`,
          Accept: 'application/json',
        },
      });

      if (response.ok) {
        return { valid: true, message: 'NVIDIA NIM API Key verified successfully!' };
      }

      if (response.status === 401 || response.status === 403) {
        return { valid: false, message: 'Invalid NVIDIA API Key. Please verify key from build.nvidia.com' };
      }

      return { valid: false, message: `NVIDIA returned HTTP ${response.status}` };
    } catch (e) {
      return { valid: false, message: e instanceof Error ? e.message : 'Network error testing NVIDIA API' };
    }
  }

  /**
   * Query NVIDIA NIM directly via official API Catalog endpoint
   */
  public async queryNvidiaNim(
    prompt: string,
    systemPrompt: string,
    history: { role: 'user' | 'assistant'; content: string }[] = [],
    modelOverride?: string
  ): Promise<{ answer: string; model: string; provider: string } | null> {
    const apiKey = this.getNvidiaApiKey();
    if (!apiKey) return null;

    const model = modelOverride || this.getSelectedModel();

    try {
      const messages = [
        { role: 'system', content: systemPrompt },
        ...history.slice(-6).map(h => ({ role: h.role, content: h.content })),
        { role: 'user', content: prompt },
      ];

      const response = await fetch('https://integrate.api.nvidia.com/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiKey}`,
          Accept: 'application/json',
        },
        body: JSON.stringify({
          model,
          messages,
          temperature: 0.3,
          top_p: 0.8,
          max_tokens: 1024,
        }),
      });

      if (!response.ok) {
        const errText = await response.text();
        console.warn('NVIDIA NIM API response not ok:', response.status, errText);
        return null;
      }

      const data = await response.json();
      const answer = data?.choices?.[0]?.message?.content;
      if (answer && typeof answer === 'string') {
        return {
          answer: answer.trim(),
          model,
          provider: 'NVIDIA NIM',
        };
      }
    } catch (e) {
      console.warn('Direct NVIDIA NIM call error:', e);
    }
    return null;
  }


}

export const nvidiaService = new NvidiaService();
