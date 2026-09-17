import { useEffect, useState } from 'react';
import { Rich } from '../lib/rich';

export interface MessageData {
  id: number;
  role: 'user' | 'ai';
  text: string;
  source?: string;
  lang?: string;
  elapsed?: number;
  followups?: string[];
}

const SOURCE_LABEL: Record<string, string> = {
  llm: '✦ AI አእምሮ',
  creative: '✦ ፈጠራ',
  memory: 'ትዝታ',
  math: 'ሒሳብ',
  dictionary: 'መዝገበ ቃላት',
  time: 'ሰዓት',
  date: 'ቀን',
};

function label(source?: string): string | null {
  if (!source) return null;
  if (source.startsWith('intent:')) return 'እውቀት';
  return SOURCE_LABEL[source] ?? null;
}

interface Props {
  msg: MessageData;
  translateOn: boolean;
  translate: (text: string) => Promise<string>;
  onFollowup?: (q: string) => void;
}

export function Message({ msg, translateOn, translate, onFollowup }: Props) {
  const [translated, setTranslated] = useState<string | null>(null);
  const [loadingTr, setLoadingTr] = useState(false);

  useEffect(() => {
    if (!translateOn || !msg.text.trim()) return;
    let alive = true;
    setLoadingTr(true);
    translate(msg.text)
      .then((t) => alive && setTranslated(t))
      .catch(() => alive && setTranslated('—'))
      .finally(() => alive && setLoadingTr(false));
    return () => {
      alive = false;
    };
  }, [translateOn, msg.text, translate]);

  const isUser = msg.role === 'user';

  return (
    <div className={`msg ${isUser ? 'user' : 'ai'}`}>
      <div className="avatar">{isUser ? 'አን' : 'ሕ'}</div>
      <div className="body">
        <div className="bubble">
          {isUser ? <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{msg.text}</p> : <Rich text={msg.text} />}

          {translateOn && (
            <div className="translation" style={{ marginTop: 10, borderTop: '1px dashed var(--line)', paddingTop: 8 }}>
              <span className="eyebrow" style={{ fontSize: '0.62rem' }}>EN</span>
              <div style={{ color: 'var(--ink-soft)', fontSize: '0.94rem' }}>
                {loadingTr ? '…' : translated || '—'}
              </div>
            </div>
          )}
        </div>

        {!isUser && msg.followups && msg.followups.length > 0 && (
          <div className="chips">
            {msg.followups.slice(0, 4).map((q) => (
              <button key={q} className="chip" onClick={() => onFollowup?.(q)}>
                ↪ {q}
              </button>
            ))}
          </div>
        )}

        <div className="meta">
          {label(msg.source) && <span>{label(msg.source)}</span>}
          {typeof msg.elapsed === 'number' && <span>{msg.elapsed} ms</span>}
        </div>
      </div>
    </div>
  );
}
