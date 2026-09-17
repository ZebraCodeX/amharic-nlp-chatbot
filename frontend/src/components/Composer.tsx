import type { KeyboardEvent, RefObject } from 'react';

interface Props {
  inputRef: RefObject<HTMLTextAreaElement>;
  onSend: () => void;
  sending: boolean;
  translateOn: boolean;
  onToggleTranslate: () => void;
  keyboardOpen: boolean;
  onToggleKeyboard: () => void;
}

export function Composer({
  inputRef,
  onSend,
  sending,
  translateOn,
  onToggleTranslate,
  keyboardOpen,
  onToggleKeyboard,
}: Props) {
  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  return (
    <div className="composer">
      <div className="composer-inner">
        <div className="composer-box">
          <textarea
            ref={inputRef}
            className="composer-input"
            rows={1}
            placeholder="በአማርኛ ጻፍልኝ…  (selam → ሰላም)"
            onKeyDown={onKeyDown}
          />
          <button className="send-btn" onClick={onSend} disabled={sending} title="ላክ (Enter)">
            ላክ
          </button>
        </div>

        <div className="composer-tools">
          <button
            className={`tool-toggle${keyboardOpen ? ' on' : ''}`}
            onClick={onToggleKeyboard}
            type="button"
          >
            <span className="dot" /> ⌨ የአማርኛ ኪቦርድ
          </button>
          <button
            className={`tool-toggle${translateOn ? ' on' : ''}`}
            onClick={onToggleTranslate}
            type="button"
          >
            <span className="dot" /> EN ⇄ አማ
          </button>
          <span className="hint">Enter ለመላክ · Shift+Enter አዲስ መስመር</span>
        </div>
      </div>
    </div>
  );
}
