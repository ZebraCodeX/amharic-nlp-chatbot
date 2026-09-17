import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { LlmStatus } from '../api/types';

/**
 * Real connectivity status: browser online/offline events plus a periodic
 * health ping to the Zer server. Returns the LLM brain status separately so
 * "connected" and "has a generative model" are never confused.
 */
export function useOnline(pollMs = 30000) {
  const [online, setOnline] = useState<boolean>(
    typeof navigator === 'undefined' ? true : navigator.onLine,
  );
  const [llm, setLlm] = useState<LlmStatus | null>(null);

  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    const ping = async () => {
      try {
        const h = await api.health();
        setOnline(true);
        setLlm(h.llm ?? null);
      } catch {
        setOnline(false);
      }
    };
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    ping();
    const timer = window.setInterval(ping, pollMs);
    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
      window.clearInterval(timer);
    };
  }, [pollMs]);

  return { online, llm };
}
