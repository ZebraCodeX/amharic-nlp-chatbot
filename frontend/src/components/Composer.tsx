import type { KeyboardEvent, RefObject } from 'react';

interface Props {
  inputRef: RefObject<HTMLTextAreaElement>;
  onSend: () => void;
  sending: boolean;
  recording: boolean;
  onToggleMic: () => void;
  live: boolean;
  onToggleLive: () => void;
  listening: boolean;
  onToggleWake: () => void;
  translateOn: boolean;
  onToggleTranslate: () => void;
  keyboardOpen: boolean;
  onToggleKeyboard: () => void;
  voiceAvailable: boolean;
  lastLang: string;
  voiceError: string | null;
}

export function Composer({
  inputRef,
  onSend,
  sending,
  recording,
  onToggleMic,
  live,
  onToggleLive,
  listening,
  onToggleWake,
  translateOn,
  onToggleTranslate,
  keyboardOpen,
  onToggleKeyboard,
  voiceAvailable,
  lastLang,
  voiceError,
}: Props) {
  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  const langLabel = lastLang === 'am' ? 'አማርኛ' : lastLang === 'en' ? 'English' : '';

  return (
    <div className="composer">
      <div className="composer-inner">
        <div className="composer-box">
          <button
            className={`mic-btn small${recording ? ' recording' : ''}`}
            onClick={onToggleMic}
            disabled={sending || live}
            type="button"
            title={voiceAvailable ? 'ተናገር (Whisper STT)' : 'ተናገር (browser)'}
          >
            {recording ? '⏹' : '🎙'}
          </button>
          <textarea
            ref={inputRef}
            className="composer-input"
            rows={1}
            placeholder="በአማርኛ ወይም English ጻፍ…  (selam → ሰላም)"
            onKeyDown={onKeyDown}
          />
          <button className="send-btn" onClick={onSend} disabled={sending} title="ላክ (Enter)">
            ላክ
          </button>
        </div>

        <div className="composer-tools">
          <button
            className={`tool-toggle${live ? ' on' : ''}`}
            onClick={onToggleLive}
            type="button"
            title="Live conversation — speak back and forth continuously"
          >
            <span className="dot" /> 🔴 ቀጥታ ውይይት
          </button>
          <button className={`tool-toggle${listening ? ' on' : ''}`} onClick={onToggleWake} type="button">
            <span className="dot" /> Hey Zer
          </button>
          <button className={`tool-toggle${keyboardOpen ? ' on' : ''}`} onClick={onToggleKeyboard} type="button">
            <span className="dot" /> ⌨ ኪቦርድ
          </button>
          <button className={`tool-toggle${translateOn ? ' on' : ''}`} onClick={onToggleTranslate} type="button">
            <span className="dot" /> EN ⇄ አማ
          </button>
          {(langLabel || voiceError) && (
            <span className="hint">{voiceError ? voiceError : `የመጨረሻ ቋንቋ፦ ${langLabel}`}</span>
          )}
        </div>
      </div>
    </div>
  );
}
