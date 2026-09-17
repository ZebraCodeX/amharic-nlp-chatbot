import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { ChatTurn, SpeechStatus } from '../api/types';
import { AmharicKeyboardPanel } from '../components/AmharicKeyboardPanel';
import { Composer } from '../components/Composer';
import { Message, type MessageData } from '../components/Message';
import {
  base64ToBlobUrl,
  createWakeWord,
  speak,
  startRecording,
  type Recorder,
  type WakeWord,
} from '../lib/audio';

const STARTERS = [
  { text: 'AI ምንድን ነው?', hint: 'በዝርዝር ማብራሪያ' },
  { text: 'ስለ ኢትዮጵያ ንገረኝ', hint: 'ታሪክና ባህል' },
  { text: 'ፓይቶን ኮድ ጻፍልኝ', hint: 'የሚሠራ ምሳሌ' },
  { text: '5 ጠቅላላ 7', hint: 'ሒሳብ' },
  { text: 'ስለ ቡና ግጥም ጻፍልኝ', hint: 'ፈጠራ' },
  { text: 'ስንት ሰዓት ነው?', hint: 'ቀንና ሰዓት' },
];

let seq = 1;

export function ChatPage() {
  const [messages, setMessages] = useState<MessageData[]>([]);
  const [sending, setSending] = useState(false);
  const [translateOn, setTranslateOn] = useState(false);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [speakReplies, setSpeakReplies] = useState(true);
  const [recording, setRecording] = useState(false);
  const [listening, setListening] = useState(false);
  const [speech, setSpeech] = useState<SpeechStatus | null>(null);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [lastLang, setLastLang] = useState<string>('');

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const recorderRef = useRef<Recorder | null>(null);
  const wakeRef = useRef<WakeWord | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    api.speechStatus().then(setSpeech).catch(() => setSpeech(null));
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

  const playUrl = useCallback((url: string) => {
    audioRef.current?.pause();
    const a = new Audio(url);
    audioRef.current = a;
    a.play().catch(() => {});
  }, []);

  /** Zer talks back in the user's language (server TTS, else the browser voice). */
  const speakReply = useCallback(
    async (text: string, lang: string | undefined) => {
      const l = lang === 'en' ? 'en' : 'am';
      if (speech?.tts?.available) {
        try {
          const blob = await api.synthesize(text, l);
          if (blob) {
            playUrl(URL.createObjectURL(blob));
            return;
          }
        } catch {
          /* fall through to the browser voice */
        }
      }
      speak(text, l);
    },
    [speech, playUrl],
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
      const snapshot = messages;
      addMsg({ role: 'user', text });
      setSending(true);
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
        inputRef.current?.focus();
        scrollDown();
      }
    },
    [messages, sending, addMsg, history, scrollDown, speakReplies, speakReply],
  );

  const sendAudio = useCallback(
    async (blob: Blob) => {
      setSending(true);
      setVoiceError(null);
      scrollDown();
      try {
        const res = await api.voiceTurn(blob, { history: history(messages) });
        if (!res.transcript) {
          setVoiceError('ድምጽ አልተሰማም። እንደገና ተናገር። / I did not catch that.');
          return;
        }
        setLastLang(res.language || '');
        addMsg({ role: 'user', text: res.transcript, lang: res.language });
        addMsg({ role: 'ai', text: res.reply, source: res.source, followups: res.followups });
        if (res.audio_b64) playUrl(base64ToBlobUrl(res.audio_b64, res.audio_mime || 'audio/wav'));
        else await speakReply(res.reply, res.language);
      } catch {
        setVoiceError('የድምጽ ስህተት / voice error');
      } finally {
        setSending(false);
        scrollDown();
      }
    },
    [messages, addMsg, history, scrollDown, speakReply, playUrl],
  );

  const sendBrowserVoice = useCallback(() => {
    const Ctor =
      (window as unknown as { SpeechRecognition?: any; webkitSpeechRecognition?: any })
        .SpeechRecognition ||
      (window as unknown as { webkitSpeechRecognition?: any }).webkitSpeechRecognition;
    if (!Ctor) {
      setVoiceError('Browser speech recognition is unavailable — use Chrome, Edge or Safari.');
      return;
    }
    const rec = new Ctor();
    rec.lang = 'am-ET';
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = async (e: any) => {
      const text = String(e.results[0][0].transcript || '');
      addMsg({ role: 'user', text });
      setSending(true);
      try {
        const reply = await api.chat(text, history(messages));
        addMsg({ role: 'ai', text: reply.reply, source: reply.source, followups: reply.followups });
        setLastLang(reply.lang || '');
        await speakReply(reply.reply, reply.lang);
      } catch {
        setVoiceError('error contacting Zer');
      } finally {
        setSending(false);
      }
    };
    rec.onerror = () => {
      setSending(false);
      setVoiceError('microphone error');
    };
    rec.start();
    setSending(true);
  }, [messages, addMsg, history, speakReply]);

  const startListening = useCallback(async () => {
    if (sending) return;
    if (speech?.stt?.available) {
      try {
        recorderRef.current = await startRecording(1900);
        setRecording(true);
      } catch {
        setVoiceError('Microphone permission was denied.');
      }
    } else {
      sendBrowserVoice();
    }
  }, [sending, speech, sendBrowserVoice]);

  const stopListening = useCallback(async () => {
    const r = recorderRef.current;
    if (!r) return;
    recorderRef.current = null;
    setRecording(false);
    const blob = await r.stop();
    if (blob.size > 1200) await sendAudio(blob);
    else setVoiceError('አጭር ድምጽ ነው / clip too short');
  }, [sendAudio]);

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
            በአማርኛ ወይም በእንግሊዝኛ ጻፍ ወይም <b>🎙 ተናገር</b> — ዘር ቋንቋህን ለይቶ በዚያ ቋንቋ
            መልሶ ይናገራል። <b>“Hey Zer”</b> ብለህም መጥራት ትችላለህ።
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
