import { useCallback, useRef, useState } from 'react';
import { api } from '../api/client';
import type { ChatTurn } from '../api/types';
import { AmharicKeyboardPanel } from '../components/AmharicKeyboardPanel';
import { Composer } from '../components/Composer';
import { Message, type MessageData } from '../components/Message';

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

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const translate = useCallback(
    (text: string) => api.translate(text, 'en').then((r) => r.translated || '—'),
    [],
  );

  const scrollDown = useCallback(() => {
    requestAnimationFrame(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }));
  }, []);

  const send = useCallback(
    async (forced?: string) => {
      const el = inputRef.current;
      const text = (forced ?? el?.value ?? '').trim();
      if (!text || sending) return;
      if (el && !forced) el.value = '';

      const history: ChatTurn[] = messages.slice(-6).map((m) =>
        m.role === 'user'
          ? { role: 'user', content: m.text }
          : { role: 'assistant', content: m.text },
      );

      setMessages((prev) => [...prev, { id: seq++, role: 'user', text }]);
      setSending(true);
      scrollDown();
      try {
        const res = await api.chat(text, history);
        setMessages((prev) => [
          ...prev,
          {
            id: seq++,
            role: 'ai',
            text: res.reply,
            source: res.source,
            elapsed: res.elapsed_ms,
            followups: res.followups,
          },
        ]);
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            id: seq++,
            role: 'ai',
            text: 'ይቅርታ፣ ትርጉሙን ማግኘት አልቻልኩም። እንደገና ሞክር።',
            source: 'error',
          },
        ]);
      } finally {
        setSending(false);
        inputRef.current?.focus();
        scrollDown();
      }
    },
    [messages, sending, scrollDown],
  );

  return (
    <div className="chat-wrap">
      {messages.length === 0 ? (
        <div className="starters">
          <span className="eyebrow">ሕሳር · የአማርኛ AI</span>
          <h1>ሰላም! ምን ልርዳህ?</h1>
          <p>
            ስለ ማንኛውም ርዕስ በዝርዝር ጠይቀኝ፣ ሂሳብ አስላ፣ ኮድ አስጻፍ ወይም ግጥም አዘጋጅ።
          </p>
          <div className="starter-grid">
            {STARTERS.map((s) => (
              <button
                key={s.text}
                className="starter"
                onClick={() => {
                  if (inputRef.current) inputRef.current.value = '';
                  send(s.text);
                }}
              >
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
              onFollowup={(q) => send(q)}
            />
          ))}
          {sending && (
            <div className="msg ai">
              <div className="avatar">ሕ</div>
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
        onSend={() => send()}
        sending={sending}
        translateOn={translateOn}
        onToggleTranslate={() => setTranslateOn((v) => !v)}
        keyboardOpen={keyboardOpen}
        onToggleKeyboard={() => setKeyboardOpen((v) => !v)}
      />

      {keyboardOpen && (
        <AmharicKeyboardPanel
          targetRef={inputRef}
          open={keyboardOpen}
          onSubmit={() => send()}
          translateEnabled={() => translateOn}
          translateFetch={translate}
        />
      )}
    </div>
  );
}
