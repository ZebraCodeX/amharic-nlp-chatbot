import type {
  ChatReply,
  ChatTurn,
  LettersList,
  LlmStatus,
  ReviewItem,
  ReviewList,
  ReviewStats,
  SpeechStatus,
  TranslateResult,
  VerifyResult,
  VoiceTurn,
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
    letter?: string;
  }): Promise<ReviewList> {
    return request<ReviewList>(`/translations/${qs(params)}`);
  },

  reviewStats(): Promise<ReviewStats> {
    return request<ReviewStats>('/translations/stats/');
  },

  translationLetters(): Promise<LettersList> {
    return request<LettersList>('/translations/letters/');
  },

  dictionaryLetters(): Promise<LettersList> {
    return request<LettersList>('/dictionary/letters/');
  },

  dictionaryByLetter(
    letter: string,
    limit = 200,
    offset = 0,
  ): Promise<{ letter: string; total: number; words: { w: string; f: number }[] }> {
    return request(`/dictionary/${qs({ letter, limit, offset })}`);
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

  speechStatus(): Promise<SpeechStatus> {
    return request<SpeechStatus>('/speech/status/');
  },

  /** One hands-free round trip: audio in → transcript + reply + spoken reply. */
  async voiceTurn(
    audio: Blob,
    opts: { lang?: string; history?: ChatTurn[] } = {},
  ): Promise<VoiceTurn> {
    const form = new FormData();
    form.append('audio', audio, 'clip.webm');
    if (opts.lang) form.append('lang', opts.lang);
    if (opts.history) form.append('history', JSON.stringify(opts.history));
    // No explicit Content-Type: the browser must set the multipart boundary.
    const res = await fetch(`${BASE}/voice/turn/`, { method: 'POST', body: form });
    if (!res.ok) throw new Error(`${res.status} ${await res.text().catch(() => '')}`);
    return (await res.json()) as VoiceTurn;
  },

  /** Server-side open-source TTS → a playable Blob. */
  async synthesize(text: string, lang = 'am'): Promise<Blob | null> {
    const res = await fetch(`${BASE}/speech/synthesize/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, lang }),
    });
    if (!res.ok) return null;
    return res.blob();
  },
};

export type { ReviewItem };
