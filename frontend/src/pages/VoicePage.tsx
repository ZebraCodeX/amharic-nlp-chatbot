import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { ChatTurn, SpeechStatus } from '../api/types';
import {
  base64ToBlobUrl,
  createWakeWord,
  speak,
  startRecording,
  type Recorder,
  type WakeWord,
} from '../lib/audio';

interface Msg {
  id: number;
  role: 'user' | 'zer';
  text: string;
  lang?: string;
}

let seq = 1;

export function VoicePage() {
  const [status, setStatus] = useState<SpeechStatus | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [mode, setMode] = useState<'auto' | 'en' | 'am'>('auto');
  const [error, setError] = useState<string | null>(null);
  const [providers, setProviders] = useState<string>('');

  const recorderRef = useRef<Recorder | null>(null);
  const wakeRef = useRef<WakeWord | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    api.speechStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const history = useCallback(
    (): ChatTurn[] =>
      messages
        .slice(-6)
        .map((m) =>
          m.role === 'user'
            ? { role: 'user', content: m.text }
            : { role: 'assistant', content: m.text },
        ),
    [messages],
  );

  const playUrl = useCallback((url: string) => {
    audioRef.current?.pause();
    const a = new Audio(url);
    audioRef.current = a;
    a.play().catch(() => {});
  }, []);

  const addMsg = (m: Omit<Msg, 'id'>) => setMessages((prev) => [...prev, { ...m, id: seq++ }]);

  const runServerTurn = useCallback(
    async (blob: Blob) => {
      setBusy(true);
      setError(null);
      try {
        const res = await api.voiceTurn(blob, {
          lang: mode === 'auto' ? undefined : mode,
          history: history(),
        });
        if (!res.transcript) {
          setError('ድምጽ አልተሰማም። እንደገና ተናገር። / I did not catch that.');
          return;
        }
        addMsg({ role: 'user', text: res.transcript, lang: res.language });
        if (res.reply) {
          addMsg({ role: 'zer', text: res.reply, lang: res.language });
          if (res.audio_b64) playUrl(base64ToBlobUrl(res.audio_b64, res.audio_mime || 'audio/wav'));
          else speak(res.reply, res.language === 'am' ? 'am' : 'en');
        }
        setProviders(`${res.stt_provider || ''} → ${res.tts_provider || ''}`);
      } catch (e) {
        setError(`ስህተት / error: ${(e as Error).message}`);
      } finally {
        setBusy(false);
      }
    },
    [mode, history, playUrl],
  );

  const runBrowserTurn = useCallback(() => {
    const Ctor =
      (window as unknown as { SpeechRecognition?: any; webkitSpeechRecognition?: any })
        .SpeechRecognition ||
      (window as unknown as { webkitSpeechRecognition?: any }).webkitSpeechRecognition;
    if (!Ctor) {
      setError('Browser speech recognition is unavailable — use Chrome, Edge or Safari.');
      return;
    }
    const rec = new Ctor();
    rec.lang = mode === 'am' ? 'am-ET' : 'en-US';
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = async (e: any) => {
      const text = String(e.results[0][0].transcript || '');
      addMsg({ role: 'user', text });
      setBusy(true);
      try {
        const reply = await api.chat(text, history());
        addMsg({ role: 'zer', text: reply.reply, lang: reply.lang });
        speak(reply.reply, reply.lang === 'en' ? 'en' : 'am');
      } catch {
        setError('error contacting Zer');
      } finally {
        setBusy(false);
      }
    };
    rec.onerror = () => {
      setBusy(false);
      setError('microphone error');
    };
    rec.start();
    setBusy(true);
  }, [mode, history]);

  const startListening = useCallback(async () => {
    if (busy) return;
    if (status?.stt?.available) {
      try {
        recorderRef.current = await startRecording(1900);
        setRecording(true);
      } catch {
        setError('Microphone permission was denied.');
      }
    } else {
      runBrowserTurn();
    }
  }, [busy, status, runBrowserTurn]);

  const stopListening = useCallback(async () => {
    const r = recorderRef.current;
    if (!r) return;
    recorderRef.current = null;
    setRecording(false);
    const blob = await r.stop();
    if (blob.size > 1200) runServerTurn(blob);
    else setError('አጭር ድምጽ ነው / clip too short');
  }, [runServerTurn]);

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
      setError("Wake word needs the browser's speech recognition (Chrome/Edge/Safari).");
      return;
    }
    w.start();
    wakeRef.current = w;
    setListening(true);
    setError(null);
  }, [listening, startListening]);

  useEffect(
    () => () => {
      wakeRef.current?.stop();
      recorderRef.current?.cancel();
      audioRef.current?.pause();
      window.speechSynthesis?.cancel();
    },
    [],
  );

  const sttLabel = status?.stt?.available ? `Whisper (${status.stt.model})` : 'browser';
  const ttsLabel = status?.tts?.available
    ? status.tts.mms
      ? 'MMS-TTS / eSpeak'
      : 'eSpeak NG'
    : 'browser voice';

  return (
    <div className="wrap">
      <span className="eyebrow">ድምጽ · Voice</span>
      <h1 className="section-title">ከዘር ጋር ውይይት</h1>
      <p className="lede">
        በአማርኛ ወይም በእንግሊዝኛ ተናገር — ዘር ቋንቋውን በራሱ ለይቶ በዚያ ቋንቋ ይመልስልሃል።
        Speak Amharic or English — Zer detects the language and answers in it.
      </p>

      <div className="voice-status">
        <span className="badge">STT: {sttLabel}</span>
        <span className="badge">TTS: {ttsLabel}</span>
        <span className="badge">Mode: {mode}</span>
        {providers && <span className="badge">{providers}</span>}
      </div>

      <div className="voice-stage">
        <div className="chat-stream">
          {messages.length === 0 && (
            <div className="center-note">
              🎙 {listening ? '“Hey Zer” ብለህ ጥራ — ዘር ያዳምጣል።' : 'ማይኩን ተጭነህ ተናገር ወይም “Hey Zer” አብር።'}
            </div>
          )}
          {messages.map((m) => (
            <div key={m.id} className={`msg ${m.role === 'user' ? 'user' : 'ai'}`}>
              <div className="avatar">{m.role === 'user' ? 'አን' : 'ዘ'}</div>
              <div className="body">
                <div className="bubble">
                  <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{m.text}</p>
                </div>
                <div className="meta">
                  {m.lang && <span>{m.lang === 'am' ? 'አማርኛ' : m.lang === 'en' ? 'English' : m.lang}</span>}
                </div>
              </div>
            </div>
          ))}
          {busy && (
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
        </div>

        <div className="voice-controls">
          <button
            className={`mic-btn${recording ? ' recording' : ''}`}
            onClick={toggleMic}
            disabled={busy}
            title="Push to talk"
          >
            {recording ? '⏹' : '🎙'}
          </button>
          <button className={`tool-toggle${listening ? ' on' : ''}`} onClick={toggleWake} type="button">
            <span className="dot" /> Hey Zer
          </button>
          <select
            className="mode-select"
            value={mode}
            onChange={(e) => setMode(e.target.value as 'auto' | 'en' | 'am')}
          >
            <option value="auto">Auto detect</option>
            <option value="am">አማርኛ</option>
            <option value="en">English</option>
          </select>
          {messages.length > 0 && (
            <button className="tool-toggle" type="button" onClick={() => setMessages([])}>
              ↺ አጽዳ
            </button>
          )}
        </div>
        {error && <div className="voice-error">{error}</div>}
      </div>
    </div>
  );
}
