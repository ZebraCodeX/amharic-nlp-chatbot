import type {
  AuthPayload,
  ChatReply,
  ChatTurn,
  Conversation,
  Health,
  LearningStats,
  LettersList,
  LlmStatus,
  MemoryItem,
  ReviewItem,
  ReviewList,
  ReviewStats,
  SpeechStatus,
  TranslateResult,
  User,
  VerifyResult,
  VoiceSettings,
  VoicesResponse,
  VoiceTurn,
} from './types';

export type { User };

declare global {
  interface Window {
    hisar?: { apiBase?: string };
    Capacitor?: { isNativePlatform?: () => boolean };
  }
}

const HOSTED_API = 'https://am-ai.fly.dev';
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

/** Absolute API origin for non-`request` callers (the keyboard web component). */
export function apiOrigin(): string {
  return ORIGIN;
}

/** Build an absolute URL to a backend path (works on native/desktop shells). */
export function apiUrl(path: string): string {
  return `${ORIGIN}${path.startsWith('/') ? path : `/${path}`}`;
}

let _token: string | null = null;
let _onUnauthorized: (() => void) | null = null;

export function setAuthToken(token: string | null): void {
  _token = token;
}
export function setUnauthorizedHandler(fn: (() => void) | null): void {
  _onUnauthorized = fn;
}

function authHeaders(): Record<string, string> {
  return _token ? { Authorization: `Token ${_token}` } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
    ...authHeaders(),
    ...((init?.headers as Record<string, string> | undefined) || {}),
  };
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (res.status === 401 && _token) {
    _onUnauthorized?.();
  }
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
  chat(text: string, history?: ChatTurn[], conversation?: number): Promise<ChatReply> {
    return request<ChatReply>('/chat/', {
      method: 'POST',
      body: JSON.stringify({ text, history, conversation }),
    });
  },

  /**
   * SSE chat: streams the reply as the model generates it, resolving with the
   * final result once the server sends it (same shape as `chat`).
   */
  chatStream(
    text: string,
    history?: ChatTurn[],
    conversation?: number,
    onDelta?: (delta: string) => void,
  ): Promise<ChatReply> {
    return new Promise<ChatReply>((resolve, reject) => {
      fetch(`${BASE}/chat/stream/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
          ...authHeaders(),
        },
        body: JSON.stringify({ text, history, conversation }),
        credentials: 'same-origin',
      })
        .then(async (res) => {
          if (!res.ok || !res.body) throw new Error(`${res.status} ${res.statusText}`);
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() ?? '';
            for (const line of lines) {
              const trimmed = line.trim();
              if (!trimmed.startsWith('data:')) continue;
              const payload = trimmed.slice(5).trim();
              if (payload === '[DONE]') continue;
              let ev: { delta?: string };
              try {
                ev = JSON.parse(payload);
              } catch {
                continue;
              }
              if (typeof ev.delta === 'string') {
                onDelta?.(ev.delta);
              } else {
                reader.cancel();
                resolve(ev as unknown as ChatReply);
                return;
              }
            }
          }
          throw new Error('stream ended without a result');
        })
        .catch(reject);
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

  learningStats(): Promise<LearningStats> {
    return request<LearningStats>('/learning/stats/');
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

  speechVoices(): Promise<VoicesResponse> {
    return request<VoicesResponse>('/speech/voices/');
  },

  health(): Promise<Health> {
    return request<Health>('/health/');
  },

  // ---- auth ----
  register(body: { username: string; password: string; display_name?: string; email?: string }) {
    return request<AuthPayload>('/auth/register/', { method: 'POST', body: JSON.stringify(body) });
  },
  login(body: { username: string; password: string }) {
    return request<AuthPayload>('/auth/login/', { method: 'POST', body: JSON.stringify(body) });
  },
  logout() {
    return request<{ ok: boolean }>('/auth/logout/', { method: 'POST' });
  },
  me() {
    return request<User>('/auth/me/');
  },

  // ---- conversations + memories ----
  listConversations() {
    return request<{ conversations: Conversation[] }>('/conversations/');
  },
  createConversation(title = '') {
    return request<Conversation>('/conversations/', {
      method: 'POST',
      body: JSON.stringify({ title }),
    });
  },
  getConversation(id: number) {
    return request<Conversation>(`/conversations/${id}/`);
  },
  renameConversation(id: number, title: string) {
    return request<Conversation>(`/conversations/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    });
  },
  deleteConversation(id: number) {
    return request<{ ok: boolean }>(`/conversations/${id}/`, { method: 'DELETE' });
  },
  listMemories() {
    return request<{ memories: MemoryItem[] }>('/memories/');
  },
  deleteMemory(id: number) {
    return request<{ ok: boolean }>('/memories/', {
      method: 'DELETE',
      body: JSON.stringify({ id }),
    });
  },

  /** One hands-free round trip: audio in → transcript + reply + spoken reply. */
  async voiceTurn(
    audio: Blob,
    opts: {
      lang?: string;
      history?: ChatTurn[];
      voice?: Record<string, string | number | undefined>;
    } = {},
  ): Promise<VoiceTurn> {
    const t = (audio.type || '').toLowerCase();
    const ext = t.includes('mp4') || t.includes('aac')
      ? 'm4a'
      : t.includes('ogg')
        ? 'ogg'
        : 'webm';
    const form = new FormData();
    form.append('audio', audio, `clip.${ext}`);
    if (opts.lang) form.append('lang', opts.lang);
    if (opts.history) form.append('history', JSON.stringify(opts.history));
    if (opts.voice) {
      Object.entries(opts.voice).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') form.append(k, String(v));
      });
    }
    // No explicit Content-Type: the browser must set the multipart boundary.
    const res = await fetch(`${BASE}/voice/turn/`, {
      method: 'POST',
      body: form,
      headers: { ...authHeaders() },
    });
    if (!res.ok) throw new Error(`${res.status} ${await res.text().catch(() => '')}`);
    return (await res.json()) as VoiceTurn;
  },

  /** Server-side open-source TTS → a playable Blob (voice is tunable). */
  async synthesize(
    text: string,
    lang = 'am',
    voice?: Record<string, string | number | undefined>,
  ): Promise<Blob | null> {
    const res = await fetch(`${BASE}/speech/synthesize/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ text, lang, ...(voice || {}) }),
    });
    if (!res.ok) return null;
    return res.blob();
  },
};

export type { ReviewItem };
