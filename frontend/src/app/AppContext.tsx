import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';
import { api, setAuthToken, setUnauthorizedHandler } from '../api/client';
import type { Conversation, User } from '../api/types';
import { DEFAULT_VOICE, loadVoicePrefs, saveVoicePrefs, type VoicePrefs } from '../lib/voice';

const TOKEN_KEY = 'hisar.token';
const USER_KEY = 'hisar.user';

interface AppState {
  user: User | null;
  token: string | null;
  ready: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (data: { username: string; password: string; display_name?: string }) => Promise<void>;
  logout: () => void;

  conversations: Conversation[];
  activeId: number | null;
  setActiveId: (id: number | null) => void;
  refreshConversations: () => Promise<void>;
  newConversation: () => void;
  removeConversation: (id: number) => Promise<void>;

  prefs: VoicePrefs;
  setPrefs: (p: VoicePrefs) => void;
  speakReplies: boolean;
  setSpeakReplies: (v: boolean) => void;
  langMode: 'auto' | 'am' | 'en';
  setLangMode: (v: 'auto' | 'am' | 'en') => void;
  live: boolean;
  setLive: (v: boolean) => void;
  listening: boolean;
  setListening: (v: boolean) => void;
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState<User | null>(() => {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) || 'null');
    } catch {
      return null;
    }
  });
  const [ready, setReady] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);

  const [prefs, setPrefsState] = useState<VoicePrefs>(() => loadVoicePrefs());
  const [speakReplies, setSpeakReplies] = useState(true);
  const [langMode, setLangMode] = useState<'auto' | 'am' | 'en'>('auto');
  const [live, setLive] = useState(false);
  const [listening, setListening] = useState(false);

  const persistUser = (u: User | null, t: string | null) => {
    setUser(u);
    setToken(t);
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
    if (u) localStorage.setItem(USER_KEY, JSON.stringify(u));
    else localStorage.removeItem(USER_KEY);
  };

  const logout = useCallback(() => {
    api.logout().catch(() => {});
    setAuthToken(null);
    persistUser(null, null);
    setConversations([]);
    setActiveId(null);
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      const d = await api.listConversations();
      setConversations(d.conversations);
    } catch {
      /* offline or unauthenticated */
    }
  }, []);

  useEffect(() => {
    setAuthToken(token);
  }, [token]);

  useEffect(() => {
    setUnauthorizedHandler(() => logout());
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  useEffect(() => {
    (async () => {
      if (token) {
        try {
          const u = await api.me();
          persistUser(u, token);
          await refreshConversations();
        } catch {
          persistUser(null, null);
          setAuthToken(null);
        }
      }
      setReady(true);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const d = await api.login({ username, password });
    setAuthToken(d.token);
    persistUser(d.user, d.token);
    await refreshConversations();
  }, [refreshConversations]);

  const register = useCallback(
    async (data: { username: string; password: string; display_name?: string }) => {
      const d = await api.register(data);
      setAuthToken(d.token);
      persistUser(d.user, d.token);
      await refreshConversations();
    },
    [refreshConversations],
  );

  const newConversation = useCallback(() => setActiveId(null), []);

  const removeConversation = useCallback(
    async (id: number) => {
      try {
        await api.deleteConversation(id);
      } catch {
        /* ignore */
      }
      setConversations((prev) => prev.filter((c) => c.id !== id));
      setActiveId((cur) => (cur === id ? null : cur));
    },
    [],
  );

  const setPrefs = useCallback((p: VoicePrefs) => {
    setPrefsState(p);
    saveVoicePrefs(p);
  }, []);

  const value: AppState = {
    user,
    token,
    ready,
    login,
    register,
    logout,
    conversations,
    activeId,
    setActiveId,
    refreshConversations,
    newConversation,
    removeConversation,
    prefs,
    setPrefs,
    speakReplies,
    setSpeakReplies,
    langMode,
    setLangMode,
    live,
    setLive,
    listening,
    setListening,
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useApp must be used inside AppProvider');
  return ctx;
}

export { DEFAULT_VOICE };
