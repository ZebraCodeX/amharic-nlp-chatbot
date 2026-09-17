import type {
  ChatReply,
  ChatTurn,
  LlmStatus,
  ReviewItem,
  ReviewList,
  ReviewStats,
  TranslateResult,
  VerifyResult,
} from './types';

declare global {
  interface Window {
    hisar?: { apiBase?: string };
    Capacitor?: { isNativePlatform?: () => boolean };
  }
}

const HOSTED_API = 'https://hisar-amharic-ai.fly.dev';
const strip = (s: string) => s.replace(/\/+$/, '');

/**
 * Resolve the API origin for every runtime we ship:
 *  - Electron sets `window.hisar.apiBase` (preload)
 *  - the Capacitor (Android/iOS) apps talk to the hosted backend
 *  - the web build uses the same origin (Django serves both)
 */
function resolveOrigin(): string {
  if (typeof window !== 'undefined') {
    if (window.hisar?.apiBase) return strip(window.hisar.apiBase);
    if (window.Capacitor?.isNativePlatform?.()) return HOSTED_API;
  }
  const env = (import.meta.env.VITE_API_BASE as string | undefined) || '';
  return strip(env);
}

const ORIGIN = resolveOrigin();
const BASE = `${ORIGIN}/api`;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText}${text ? `: ${text.slice(0, 200)}` : ''}`);
  }
  return (await res.json()) as T;
}

function qs(params: Record<string, string | number | undefined>): string {
  const u = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') u.set(k, String(v));
  });
  const s = u.toString();
  return s ? `?${s}` : '';
}

export const api = {
  chat(text: string, history?: ChatTurn[]): Promise<ChatReply> {
    return request<ChatReply>('/chat/', {
      method: 'POST',
      body: JSON.stringify({ text, history }),
    });
  },

  translate(text: string, to: 'en' | 'am' = 'en'): Promise<TranslateResult> {
    return request<TranslateResult>(`/translate/${qs({ text, to })}`);
  },

  translations(params: {
    status?: string;
    q?: string;
    limit?: number;
    offset?: number;
    max_confidence?: number;
  }): Promise<ReviewList> {
    return request<ReviewList>(`/translations/${qs(params)}`);
  },

  reviewStats(): Promise<ReviewStats> {
    return request<ReviewStats>('/translations/stats/');
  },

  verify(body: {
    text: string;
    src?: string;
    dst?: string;
    translation: string;
    correct?: string;
  }): Promise<VerifyResult> {
    return request<VerifyResult>('/translations/verify/', {
      method: 'POST',
      body: JSON.stringify({ src: 'am', dst: 'en', ...body }),
    });
  },

  suggest(text: string): Promise<{ words: [string, number][]; next: [string, number][]; sentences: string[] }> {
    return request(`/suggest/${qs({ text })}`);
  },

  llmStatus(): Promise<LlmStatus> {
    return request<LlmStatus>('/llm-status/');
  },
};

export type { ReviewItem };
