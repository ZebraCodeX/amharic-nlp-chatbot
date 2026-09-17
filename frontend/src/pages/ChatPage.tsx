import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { ChatTurn, SpeechStatus, VoicesResponse } from '../api/types';
import { AmharicKeyboardPanel } from '../components/AmharicKeyboardPanel';
import { Composer } from '../components/Composer';
import { Message, type MessageData } from '../components/Message';
import { VoicePanel } from '../components/VoicePanel';
import {
  base64ToBlobUrl,
  createWakeWord,
  recognizeDetected,
  speak,
  startRecording,
  type Recorder,
  type WakeWord,
} from '../lib/audio';
import {
  DEFAULT_VOICE,
  loadVoicePrefs,
  paramsFor,
  saveVoicePrefs,
  turnParams,
  type VoicePrefs,
} from '../lib/voice';

const STARTERS = [
  { text: 'AI ምንድን ነው?', hint: 'በዝርዝር ማብራሪያ' },
  { text: 'ስለ ኢትዮጵያ ንገረኝ', hint: 'ታሪክና ባህል' },
  { text: 'ፓይቶን ኮድ ጻፍልኝ', hint: 'የሚሠራ ምሳሌ' },
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
  const [messages, setMessages] = useState<MessageData[]>([]);
  const [sending, setSending] = useState(false);
  const [translateOn, setTranslateOn] = useState(false);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [speakReplies, setSpeakReplies] = useState(true);
  const [recording, setRecording] = useState(false);
  const [listening, setListening] = useState(false);
  const [live, setLive] = useState(false);
  const [phase, setPhase] = useState<Phase>('idle');
  const [panelOpen, setPanelOpen] = useState(false);
  const [speech, setSpeech] = useState<SpeechStatus | null>(null);
  const [voices, setVoices] = useState<VoicesResponse | null>(null);
  const [prefs, setPrefs] = useState<VoicePrefs>(() => loadVoicePrefs());
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [lastLang, setLastLang] = useState('');
  const [langMode, setLangMode] = useState<'auto' | 'am' | 'en'>('auto');

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const recorderRef = useRef<Recorder | null>(null);
  const wakeRef = useRef<WakeWord | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const liveRef = useRef(false);
  const messagesRef = useRef<MessageData[]>([]);

  messagesRef.current = messages;

  useEffect(() => {
    api.speechStatus().then(setSpeech).catch(() => setSpeech(null));
    api.speechVoices().then(setVoices).catch(() => setVoices(null));
  }, []);

  const updatePrefs = useCallback((next: VoicePrefs) => {
    setPrefs(next);
    saveVoicePrefs(next);
  }, []);

  const scrollDown = useCallback(() => {
    requestAnimationFrame(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }));
  }, []);

  const addMsg = useCallback((m: Omit<MessageData, 'id'>) => {
    setMessages((prev) => [...prev, { ...m, id: seq++ }]);
  }, []);

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

  const playUrl = useCallback((url: string, onEnd?: () => void) => {
    audioRef.current?.pause();
    const a = new Audio(url);
    audioRef.current = a;
    if (onEnd) {
      a.onended = onEnd;
      a.onerror = onEnd;
    }
    a.play().catch(() => onEnd?.());
  }, []);

  /** Zer talks back in the user's language (server TTS, else the browser voice). */
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
        const res = await api.chat(text, history(snapshot));
        addMsg({
          role: 'ai',
          text: res.reply,
          source: res.source,
          elapsed: res.elapsed_ms,
          followups: res.followups,
        });
        setLastLang(res.lang || '');
        if (speakReplies) await speakReply(res.reply, res.lang);
      } catch {
        addMsg({ role: 'ai', text: 'ይቅርታ፣ ስህተት ተፈጥሯል። እንደገና ሞክር።', source: 'error' });
      } finally {
        setSending(false);
        setPhase('idle');
        inputRef.current?.focus();
        scrollDown();
      }
    },
    [sending, addMsg, history, scrollDown, speakReplies, speakReply],
  );

  /** One voice turn; returns after the reply audio starts playing. */
  const doVoiceTurn = useCallback(
    async (blob: Blob, onDone?: () => void) => {
      setSending(true);
      setPhase('thinking');
      setVoiceError(null);
      try {
        const res = await api.voiceTurn(blob, {
          lang: langMode === 'auto' ? undefined : langMode,
          history: history(messagesRef.current),
          voice: turnParams(prefs),
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
    [prefs, langMode, addMsg, history, playUrl, speakReply],
  );

  /* ---------------- Live (Gemini-style) conversation loop ---------------- */
  const scheduleLive = useCallback(() => {
    if (liveRef.current) setTimeout(() => liveCycleRef.current?.(), 300);
  }, []);

  const liveCycleRef = useRef<(() => void) | null>(null);

  /** Browser-recognition turn (two-pass language detection), then speak back. */
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
        const reply = await api.chat(text, history(messagesRef.current));
        addMsg({ role: 'ai', text: reply.reply, source: reply.source, followups: reply.followups });
        setLastLang(reply.lang || lang);
        setSending(false);
        setPhase('speaking');
        await speakReply(reply.reply, reply.lang || lang, onDone);
      } catch {
        setSending(false);
        setVoiceError('error contacting Zer');
        onDone?.();
      }
    },
    [langMode, addMsg, history, speakReply],
  );

  const browserLiveTurn = useCallback(() => {
    browserTurn(scheduleLive);
  }, [browserTurn, scheduleLive]);

  const liveCycle = useCallback(async () => {
    if (!liveRef.current) return;
    setPhase('listening');
    if (speech?.stt?.available) {
      let rec: Recorder;
      try {
        rec = await startRecording(1300, 15000);
      } catch {
        setVoiceError('Microphone permission was denied.');
        stopLive();
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
      browserLiveTurn();
    }
  }, [speech, doVoiceTurn, scheduleLive, browserLiveTurn]);
  liveCycleRef.current = liveCycle;

  const startLive = useCallback(() => {
    liveRef.current = true;
    setLive(true);
    setVoiceError(null);
    wakeRef.current?.stop();
    setListening(false);
    liveCycleRef.current?.();
  }, []);

  const stopLive = useCallback(() => {
    liveRef.current = false;
    setLive(false);
    setPhase('idle');
    recorderRef.current?.cancel();
    recorderRef.current = null;
    setRecording(false);
    audioRef.current?.pause();
    window.speechSynthesis?.cancel();
  }, []);

  const toggleLive = useCallback(() => {
    if (live) stopLive();
    else startLive();
  }, [live, startLive, stopLive]);

  /* ---------------- push-to-talk ---------------- */
  const startListening = useCallback(async () => {
    if (sending || live) return;
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
  }, [listening, startListening]);

  const testVoice = useCallback(() => {
    const sample = 'ሰላም! እኔ ዘር ነኝ። ይህ የድምጼ ሙከራ ነው።';
    speakReply(sample, 'am');
  }, [speakReply]);

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
            በአማርኛ ወይም በእንግሊዝኛ ጻፍ፣ <b>🎙 ተናገር</b>፣ ወይም <b>🔴 ቀጥታ ውይይት</b> አብርተህ
            እንደ ስልክ ንግግር ደጋግመህ ተነጋገር — ዘር ቋንቋህን ለይቶ በዚያ ቋንቋ ይመልስልሃል።
          </p>
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

      {phase !== 'idle' && <div className={`voice-phase ${phase}`}>{PHASE_LABEL[phase]}</div>}

      {panelOpen && (
        <VoicePanel
          voices={voices}
          prefs={prefs}
          onChange={updatePrefs}
          onTest={testVoice}
          onReset={() => updatePrefs({ ...DEFAULT_VOICE })}
        />
      )}

      <Composer
        inputRef={inputRef}
        onSend={() => sendText()}
        sending={sending}
        translateOn={translateOn}
        onToggleTranslate={() => setTranslateOn((v) => !v)}
        keyboardOpen={keyboardOpen}
        onToggleKeyboard={() => setKeyboardOpen((v) => !v)}
        recording={recording}
        listening={listening}
        onToggleMic={toggleMic}
        onToggleWake={toggleWake}
        speakReplies={speakReplies}
        onToggleSpeakReplies={() => setSpeakReplies((v) => !v)}
        voiceAvailable={!!speech?.stt?.available}
        lastLang={lastLang}
        voiceError={voiceError}
        live={live}
        onToggleLive={toggleLive}
        panelOpen={panelOpen}
        onTogglePanel={() => setPanelOpen((v) => !v)}
        phase={phase}
        langMode={langMode}
        onLangMode={setLangMode}
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
