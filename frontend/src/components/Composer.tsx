import type { KeyboardEvent, RefObject } from 'react';

interface Props {
  inputRef: RefObject<HTMLTextAreaElement>;
  onSend: () => void;
  sending: boolean;
  translateOn: boolean;
  onToggleTranslate: () => void;
  keyboardOpen: boolean;
  onToggleKeyboard: () => void;
  recording: boolean;
  listening: boolean;
  onToggleMic: () => void;
  onToggleWake: () => void;
  speakReplies: boolean;
  onToggleSpeakReplies: () => void;
  voiceAvailable: boolean;
  lastLang: string;
  voiceError: string | null;
  live: boolean;
  onToggleLive: () => void;
  panelOpen: boolean;
  onTogglePanel: () => void;
  phase: 'idle' | 'listening' | 'thinking' | 'speaking';
  langMode: 'auto' | 'am' | 'en';
  onLangMode: (mode: 'auto' | 'am' | 'en') => void;
}

export function Composer({
  inputRef,
  onSend,
  sending,
  translateOn,
  onToggleTranslate,
  keyboardOpen,
  onToggleKeyboard,
  recording,
  listening,
  onToggleMic,
  onToggleWake,
  speakReplies,
  onToggleSpeakReplies,
  voiceAvailable,
  lastLang,
  voiceError,
  live,
  onToggleLive,
  panelOpen,
  onTogglePanel,
  langMode,
  onLangMode,
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
            disabled={sending}
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
          <button
            className={`tool-toggle${panelOpen ? ' on' : ''}`}
            onClick={onTogglePanel}
            type="button"
            title="Voice type, speed, pitch and volume"
          >
            <span className="dot" /> 🎛 ድምጽ
          </button>
          <button className={`tool-toggle${listening ? ' on' : ''}`} onClick={onToggleWake} type="button">
            <span className="dot" /> Hey Zer
          </button>
          <select
            className="mode-select"
            value={langMode}
            onChange={(e) => onLangMode(e.target.value as 'auto' | 'am' | 'en')}
            title="Spoken language: auto-detect, or force Amharic/English"
          >
            <option value="auto">🌐 ቋንቋ ራሱ ይለይ · Auto</option>
            <option value="am">አማርኛ</option>
            <option value="en">English</option>
          </select>
          <button
            className={`tool-toggle${speakReplies ? ' on' : ''}`}
            onClick={onToggleSpeakReplies}
            type="button"
            title="Zer replies with audio in your language"
          >
            <span className="dot" /> 🔊 መልስ ይናገር
          </button>
          <button className={`tool-toggle${keyboardOpen ? ' on' : ''}`} onClick={onToggleKeyboard} type="button">
            <span className="dot" /> ⌨ ኪቦርድ
          </button>
          <button className={`tool-toggle${translateOn ? ' on' : ''}`} onClick={onToggleTranslate} type="button">
            <span className="dot" /> EN ⇄ አማ
          </button>
          {(langLabel || voiceError) && (
            <span className="hint">
              {voiceError ? voiceError : `የመጨረሻ ቋንቋ፦ ${langLabel}`}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
