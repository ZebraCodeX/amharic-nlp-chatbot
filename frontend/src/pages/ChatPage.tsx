import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { ChatTurn, SpeechStatus } from '../api/types';
import { useApp } from '../app/AppContext';
import { AmharicKeyboardPanel } from '../components/AmharicKeyboardPanel';
import { Composer } from '../components/Composer';
import { Message, type MessageData } from '../components/Message';
import {
  base64ToBlobUrl,
  createWakeWord,
  recognizeDetected,
  speak,
  startRecording,
  unlockAudio,
  type Recorder,
  type WakeWord,
} from '../lib/audio';
import { paramsFor, turnParams } from '../lib/voice';

const STARTERS = [
  { text: 'AI ምንድን ነው?', hint: 'በዝርዝር ማብራሪያ' },
  { text: 'ስለ ኢትዮጵያ ንገረኝ', hint: 'ታሪክና ባህል' },
  { text: 'ፓይቶን ኮድ ጻፍልኝ ድምር', hint: 'በአማርኛ ኮድ' },
  { text: '5 ጠቅላላ 7', hint: 'ሒሳብ' },
  { text: 'ስለ ቡና ግጥም ጻፍልኝ', hint: 'ፈጠራ' },
  { text: 'ስንት ሰዓት ነው?', hint: 'ቀንና ሰዓት' },
];

type Phase = 'idle' | 'listening' | 'thinking' | 'speaking';
const PHASE_LABEL: Record<Phase, string> = {
  idle: '',
  listening: '🎧 በማዳመጥ ላይ…',
  thinking: '🤔 ዘር እያሰበ ነው…',
  speaking: '🔊 ዘር ይናገራል…',
};

let seq = 1;

export function ChatPage() {
  const app = useApp();
  const { user, activeId, prefs, speakReplies, langMode, live, setLive, listening, setListening, resetNonce } = app;

  const [messages, setMessages] = useState<MessageData[]>([]);
  const [sending, setSending] = useState(false);
  const [translateOn, setTranslateOn] = useState(false);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [recording, setRecording] = useState(false);
  const [phase, setPhase] = useState<Phase>('idle');
  const [speech, setSpeech] = useState<SpeechStatus | null>(null);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [lastLang, setLastLang] = useState('');

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const recorderRef = useRef<Recorder | null>(null);
  const wakeRef = useRef<WakeWord | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const pendingEndRef = useRef<(() => void) | null>(null);
  const liveRef = useRef(false);
  const messagesRef = useRef<MessageData[]>([]);
  const convRef = useRef<number | null>(activeId);
  messagesRef.current = messages;
  convRef.current = activeId;

  useEffect(() => {
    api.speechStatus().then(setSpeech).catch(() => setSpeech(null));
    // Mobile browsers only allow audio after a user gesture.
    const unlock = () => unlockAudio();
    window.addEventListener('pointerdown', unlock, { once: true });
    window.addEventListener('touchstart', unlock, { once: true });
    return () => {
      window.removeEventListener('pointerdown', unlock);
      window.removeEventListener('touchstart', unlock);
    };
  }, []);

  // Load the selected conversation's turns (signed-in users).
  const prevActive = useRef<number | null | undefined>(undefined);
  useEffect(() => {
    if (!user) {
      // Remember where we were so signing in doesn't wipe an anonymous chat.
      prevActive.current = activeId;
      return;
    }
    if (activeId === prevActive.current) return;
    prevActive.current = activeId;
    if (activeId == null) {
      setMessages([]);
      return;
    }
    api
      .getConversation(activeId)
      .then((c) =>
        setMessages(
          (c.turns || []).map((t) => ({
            id: seq++,
            role: t.role === 'user' ? 'user' : 'ai',
            text: t.text,
            lang: t.lang,
            source: t.source,
          })),
        ),
      )
      .catch(() => {});
  }, [activeId, user]);

  // "＋ አዲስ ውይይት" clears the chat even for anonymous users (where activeId
  // is already null, so the effect above would not fire).
  useEffect(() => {
    if (resetNonce === 0) return;
    setMessages([]);
    setLastLang('');
    inputRef.current?.focus();
  }, [resetNonce]);

  const scrollDown = useCallback(() => {
    requestAnimationFrame(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }));
  }, []);

  const addMsg = useCallback((m: Omit<MessageData, 'id'>) => {
    setMessages((prev) => [...prev, { ...m, id: seq++ }]);
  }, []);

  /** Live-update the last AI bubble while an SSE reply streams in. */
  const patchLastMsg = useCallback(
    (patch: Partial<Pick<MessageData, 'text' | 'source' | 'elapsed' | 'followups'>> |
              ((current: string) => Partial<Pick<MessageData, 'text'>>)) => {
      setMessages((prev) => {
        const idx = prev.length - 1;
        if (idx < 0 || prev[idx].role !== 'ai') return prev;
        const base = prev[idx];
        const merged = typeof patch === 'function' ? patch(base.text) : patch;
        const next = prev.slice();
        next[idx] = { ...base, ...merged };
        return next;
      });
    },
    [],
  );

  const history = useCallback(
    (from: MessageData[]): ChatTurn[] =>
      from
        .slice(-6)
        .map((m) =>
          m.role === 'user'
            ? { role: 'user', content: m.text }
            : { role: 'assistant', content: m.text },
        ),
    [],
  );

  const onConversationSaved = useCallback(
    (convId?: number) => {
      if (!convId) return;
      if (convRef.current == null) app.setActiveId(convId);
      app.refreshConversations();
    },
    [app],
  );

  const playUrl = useCallback((url: string, onEnd?: () => void) => {
    audioRef.current?.pause();
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
    const a = new Audio(url);
    audioRef.current = a;
    audioUrlRef.current = url;
    const finish = () => {
      if (pendingEndRef.current === onEnd) pendingEndRef.current = null;
      if (onEnd) onEnd();
    };
    if (onEnd) {
      pendingEndRef.current = onEnd;
      a.onended = finish;
      a.onerror = finish;
    }
    a.play().catch(finish);
  }, []);

  /** Kill switch — stop Zer reading its reply out loud (server or browser TTS). */
  const stopSpeaking = useCallback(() => {
    audioRef.current?.pause();
    audioRef.current = null;
    window.speechSynthesis?.cancel();
    const end = pendingEndRef.current;
    pendingEndRef.current = null;
    setPhase('idle');
    // Let the live loop keep going after a manual stop.
    end?.();
  }, []);

  const speakReply = useCallback(
    async (text: string, lang: string | undefined, onEnd?: () => void) => {
      const l = lang === 'en' ? 'en' : 'am';
      if (speech?.tts?.available) {
        try {
          const blob = await api.synthesize(text, l, paramsFor(prefs, l));
          if (blob) {
            playUrl(URL.createObjectURL(blob), onEnd);
            return;
          }
        } catch {
          /* fall through */
        }
      }
      speak(text, l, onEnd);
    },
    [speech, prefs, playUrl],
  );

  const translate = useCallback(
    (text: string) => api.translate(text, 'en').then((r) => r.translated || '—'),
    [],
  );

  const sendText = useCallback(
    async (forced?: string) => {
      const el = inputRef.current;
      const text = (forced ?? el?.value ?? '').trim();
      if (!text || sending) return;
      if (el && !forced) el.value = '';
      const snapshot = messagesRef.current;
      addMsg({ role: 'user', text });
      setSending(true);
      setPhase('thinking');
      scrollDown();
      try {
        addMsg({ role: 'ai', text: '' });
        const res = await api.chatStream(
          text,
          history(snapshot),
          activeId ?? undefined,
          (d) => {
            patchLastMsg((t) => ({ text: t + d }));
            scrollDown();
          },
        );
        patchLastMsg({
          text: res.reply,
          source: res.source,
          elapsed: res.elapsed_ms,
          followups: res.followups,
        });
        setLastLang(res.lang || '');
        onConversationSaved((res as { conversation?: number }).conversation);
        if (speakReplies) await speakReply(res.reply, res.lang);
      } catch {
        patchLastMsg({ text: 'ይቅርታ፣ ስህተት ተፈጥሯል። እንደገና ሞክር።', source: 'error' });
      } finally {
        setSending(false);
        setPhase('idle');
        inputRef.current?.focus();
        scrollDown();
      }
    },
    [sending, activeId, addMsg, patchLastMsg, history, scrollDown, speakReplies, speakReply, onConversationSaved],
  );

  const doVoiceTurn = useCallback(
    async (blob: Blob, onDone?: () => void) => {
      setSending(true);
      setPhase('thinking');
      setVoiceError(null);
      try {
        const res = await api.voiceTurn(blob, {
          lang: langMode === 'auto' ? undefined : langMode,
          history: history(messagesRef.current),
          voice: { ...turnParams(prefs), conversation: activeId ?? undefined },
        });
        setSending(false);
        if (!res.transcript) {
          setVoiceError('ድምጽ አልተሰማም። እንደገና ተናገር።');
          onDone?.();
          return;
        }
        setLastLang(res.language || '');
        addMsg({ role: 'user', text: res.transcript, lang: res.language });
        addMsg({ role: 'ai', text: res.reply, source: res.source, followups: res.followups });
        onConversationSaved((res as { conversation?: number }).conversation);
        setPhase('speaking');
        const next = () => {
          setPhase('idle');
          onDone?.();
        };
        if (res.audio_b64) playUrl(base64ToBlobUrl(res.audio_b64, res.audio_mime || 'audio/wav'), next);
        else await speakReply(res.reply, res.language, next);
      } catch {
        setSending(false);
        setVoiceError('የድምጽ ስህተት / voice error');
        onDone?.();
      }
    },
    [prefs, langMode, activeId, addMsg, history, playUrl, speakReply, onConversationSaved],
  );

  /* ---------------- Live conversation loop ---------------- */
  const liveCycleRef = useRef<(() => void) | null>(null);
  const scheduleLive = useCallback(() => {
    if (liveRef.current) setTimeout(() => liveCycleRef.current?.(), 300);
  }, []);

  const browserTurn = useCallback(
    async (onDone?: () => void) => {
      const { text, lang } = await recognizeDetected(langMode);
      if (!text) {
        onDone?.();
        return;
      }
      addMsg({ role: 'user', text, lang });
      setSending(true);
      setPhase('thinking');
      try {
        addMsg({ role: 'ai', text: '' });
        const reply = await api.chatStream(
          text,
          history(messagesRef.current),
          activeId ?? undefined,
          (d) => {
            patchLastMsg((t) => ({ text: t + d }));
            scrollDown();
          },
        );
        patchLastMsg({
          text: reply.reply,
          source: reply.source,
          followups: reply.followups,
          elapsed: reply.elapsed_ms,
        });
        setLastLang(reply.lang || lang);
        onConversationSaved((reply as { conversation?: number }).conversation);
        setSending(false);
        setPhase('speaking');
        await speakReply(reply.reply, reply.lang || lang, onDone);
      } catch {
        setSending(false);
        setVoiceError('error contacting Zer');
        onDone?.();
      }
    },
    [langMode, activeId, addMsg, patchLastMsg, history, speakReply, onConversationSaved],
  );

  const liveCycle = useCallback(async () => {
    if (!liveRef.current) return;
    setPhase('listening');
    if (speech?.stt?.available) {
      let rec: Recorder;
      try {
        rec = await startRecording(1300, 15000);
      } catch {
        setVoiceError('Microphone permission was denied.');
        setLive(false);
        liveRef.current = false;
        return;
      }
      if (!liveRef.current) {
        rec.cancel();
        return;
      }
      recorderRef.current = rec;
      setRecording(true);
      const blob = await rec.done;
      recorderRef.current = null;
      setRecording(false);
      if (!liveRef.current) return;
      if (blob.size < 1200) {
        liveCycleRef.current?.();
        return;
      }
      await doVoiceTurn(blob, scheduleLive);
    } else {
      browserTurn(scheduleLive);
    }
  }, [speech, doVoiceTurn, scheduleLive, browserTurn, setLive]);
  liveCycleRef.current = liveCycle;

  const startLive = useCallback(() => {
    unlockAudio();
    liveRef.current = true;
    setLive(true);
    setVoiceError(null);
    wakeRef.current?.stop();
    setListening(false);
    liveCycleRef.current?.();
  }, [setLive, setListening]);

  const stopLive = useCallback(() => {
    liveRef.current = false;
    setLive(false);
    setPhase('idle');
    recorderRef.current?.cancel();
    recorderRef.current = null;
    setRecording(false);
    audioRef.current?.pause();
    window.speechSynthesis?.cancel();
  }, [setLive]);

  const toggleLive = useCallback(() => {
    if (live) stopLive();
    else startLive();
  }, [live, startLive, stopLive]);

  /* ---------------- push-to-talk ---------------- */
  const startListening = useCallback(async () => {
    if (sending || live) return;
    unlockAudio();
    if (speech?.stt?.available) {
      try {
        recorderRef.current = await startRecording(1900, 20000);
        setRecording(true);
      } catch {
        setVoiceError('Microphone permission was denied.');
      }
    } else {
      browserTurn();
    }
  }, [sending, live, speech, browserTurn]);

  const stopListening = useCallback(async () => {
    const r = recorderRef.current;
    if (!r) return;
    recorderRef.current = null;
    setRecording(false);
    const blob = await r.stop();
    if (blob.size > 1200) await doVoiceTurn(blob);
    else setVoiceError('አጭር ድምጽ ነው / clip too short');
  }, [doVoiceTurn]);

  const toggleMic = useCallback(() => {
    if (recording) stopListening();
    else startListening();
  }, [recording, startListening, stopListening]);

  const toggleWake = useCallback(() => {
    if (listening) {
      wakeRef.current?.stop();
      wakeRef.current = null;
      setListening(false);
      return;
    }
    const w = createWakeWord(() => {
      wakeRef.current = null;
      setListening(false);
      startListening();
    });
    if (!w) {
      setVoiceError("Wake word needs the browser's speech recognition (Chrome/Edge/Safari).");
      return;
    }
    w.start();
    wakeRef.current = w;
    setListening(true);
    setVoiceError(null);
  }, [listening, startListening, setListening]);

  useEffect(
    () => () => {
      wakeRef.current?.stop();
      recorderRef.current?.cancel();
      audioRef.current?.pause();
      window.speechSynthesis?.cancel();
    },
    [],
  );

  return (
    <div className="chat-wrap">
      {messages.length === 0 ? (
        <div className="starters">
          <span className="eyebrow">ዘር · Zer</span>
          <h1>ሰላም! እኔ ዘር ነኝ። ምን ልርዳህ?</h1>
          <p>
            በአማርኛ ወይም በእንግሊዝኛ ጻፍ፣ <b>🎙 ተናገር</b>፣ ወይም <b>🔴 ቀጥታ ውይይት</b> አብርተህ እንደ
            ስልክ ንግግር ደጋግመህ ተነጋገር — ዘር ቋንቋህን ለይቶ በዚያ ቋንቋ ይመልስልሃል።
          </p>
          {!user && (
            <p className="side-note" style={{ marginBottom: 18 }}>
              ውይይቶችህን እንዲያስታውስ ከጎኑ ያለውን «ግባ» ተጠቀም።
            </p>
          )}
          <div className="starter-grid">
            {STARTERS.map((s) => (
              <button key={s.text} className="starter" onClick={() => sendText(s.text)}>
                {s.text}
                <small>{s.hint}</small>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="chat-stream">
          {messages.map((m) => (
            <Message
              key={m.id}
              msg={m}
              translateOn={translateOn}
              translate={translate}
              onFollowup={(q) => sendText(q)}
            />
          ))}
          {sending && (
            <div className="msg ai">
              <div className="avatar">ዘ</div>
              <div className="body">
                <div className="bubble">
                  <span className="typing">
                    <i />
                    <i />
                    <i />
                  </span>
                </div>
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>
      )}

      {phase !== 'idle' && (
        <div
          className={`voice-phase ${phase}`}
          onClick={phase === 'speaking' ? stopSpeaking : undefined}
          role={phase === 'speaking' ? 'button' : undefined}
          style={phase === 'speaking' ? { cursor: 'pointer' } : undefined}
        >
          {phase === 'speaking' ? `${PHASE_LABEL[phase]} · ⏹ አቁም (ንካ)` : PHASE_LABEL[phase]}
        </div>
      )}

      <Composer
        inputRef={inputRef}
        onSend={() => sendText()}
        sending={sending}
        recording={recording}
        onToggleMic={toggleMic}
        live={live}
        onToggleLive={toggleLive}
        listening={listening}
        onToggleWake={toggleWake}
        translateOn={translateOn}
        onToggleTranslate={() => setTranslateOn((v) => !v)}
        keyboardOpen={keyboardOpen}
        onToggleKeyboard={() => setKeyboardOpen((v) => !v)}
        voiceAvailable={!!speech?.stt?.available}
        lastLang={lastLang}
        voiceError={voiceError}
        speaking={phase === 'speaking'}
        onStopSpeaking={stopSpeaking}
      />

      {keyboardOpen && (
        <AmharicKeyboardPanel
          targetRef={inputRef}
          open={keyboardOpen}
          onSubmit={() => sendText()}
          translateEnabled={() => translateOn}
          translateFetch={translate}
        />
      )}
    </div>
  );
}
