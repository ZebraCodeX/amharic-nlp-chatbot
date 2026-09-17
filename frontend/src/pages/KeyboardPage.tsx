import { useRef, useState } from 'react';
import { api } from '../api/client';
import { AmharicKeyboardPanel } from '../components/AmharicKeyboardPanel';

export function KeyboardPage() {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [trsOn, setTrsOn] = useState(true);

  const translate = (text: string) => api.translate(text, 'en').then((r) => r.translated || '—');

  return (
    <div className="wrap">
      <span className="eyebrow">የግዕዝ ፊደል</span>
      <h1 className="section-title">የአማርኛ ኪቦርድ</h1>
      <p className="lede">
        የፊደል ቁልፍን ነክተህ ሰባቱን የአናባቢ ቅርጾች (ሀ ሁ ሂ ሃ ሄ ህ ሆ) ምረጥ። ወይም «ላቲን → ግዕዝ»
        ቀይረህ «selam» ብለህ ጻፍ።
      </p>

      <textarea
        ref={inputRef}
        className="kbd-demo-input"
        rows={3}
        placeholder="እዚህ ጻፍ…"
        defaultValue=""
      />

      <div className="composer-tools" style={{ marginTop: -4, marginBottom: 10 }}>
        <button
          className={`tool-toggle${trsOn ? ' on' : ''}`}
          type="button"
          onClick={() => setTrsOn((v) => !v)}
        >
          <span className="dot" /> EN ⇄ አማ ትርጉም
        </button>
      </div>

      <AmharicKeyboardPanel
        targetRef={inputRef}
        open
        translateEnabled={() => trsOn}
        translateFetch={translate}
      />
    </div>
  );
}
