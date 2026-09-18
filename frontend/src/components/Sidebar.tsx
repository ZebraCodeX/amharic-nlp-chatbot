import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { api } from '../api/client';
import type { VoicesResponse } from '../api/types';
import { useApp } from '../app/AppContext';
import { DEFAULT_VOICE } from '../lib/voice';
import { AuthDialog } from './AuthDialog';
import { VoicePanel } from './VoicePanel';

function relTime(iso: string): string {
  const d = new Date(iso);
  const mins = Math.floor((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return 'አሁን';
  if (mins < 60) return `${mins} ደቂቃ`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} ሰዓት`;
  return `${Math.floor(hrs / 24)} ቀን`;
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const app = useApp();
  const [authOpen, setAuthOpen] = useState(false);
  const [voices, setVoices] = useState<VoicesResponse | null>(null);
  const [showVoice, setShowVoice] = useState(false);

  useEffect(() => {
    api.speechVoices().then(setVoices).catch(() => setVoices(null));
  }, []);

  const testVoice = () => {
    api.synthesize('ሰላም! እኔ ዘር ነኝ።', 'am', {
      voice: app.prefs.voiceAm,
      rate: app.prefs.rate,
      pitch: app.prefs.pitch,
      volume: app.prefs.volume,
    });
  };

  return (
    <aside className="sidebar">
      <NavLink to="/" className="brand" style={{ textDecoration: 'none' }} onClick={onNavigate}>
        <span className="brand-mark">ዘ</span>
        <span className="brand-text">
          <b>ዘር</b>
          <span>Zer · Amharic AI</span>
        </span>
      </NavLink>

      <div className="side-section">
        {app.user ? (
          <div className="user-row">
            <span className="avatar-circle">{app.user.name?.[0] || 'ዘ'}</span>
            <span className="user-name">{app.user.name}</span>
            <button className="link-btn" onClick={app.logout} title="ውጣ">
              ውጣ
            </button>
          </div>
        ) : (
          <button className="btn btn-gold" style={{ width: '100%' }} onClick={() => setAuthOpen(true)}>
            ግባ / Sign in
          </button>
        )}
      </div>

      <div className="side-section">
        <button
          className="btn btn-primary"
          style={{ width: '100%' }}
          onClick={() => {
            app.newConversation();
            onNavigate?.();
          }}
        >
          ＋ አዲስ ውይይት
        </button>
      </div>

      <div className="side-section conversations">
        <div className="side-label">ውይይቶች</div>
        {!app.user && <div className="side-note">ውይይቶችህን ለማስቀመጥ ግባ።</div>}
        {app.user && app.conversations.length === 0 && (
          <div className="side-note">እስካሁን ውይይት የለም።</div>
        )}
        <div className="conv-list">
          {app.conversations.map((c) => (
            <div
              key={c.id}
              className={`conv-item${app.activeId === c.id ? ' active' : ''}`}
              onClick={() => {
                app.setActiveId(c.id);
                onNavigate?.();
              }}
            >
              <span className="conv-title">{c.title || 'አዲስ ውይይት'}</span>
              <span className="conv-time">{relTime(c.updated)}</span>
              <button
                className="conv-del"
                title="አጥፋ"
                onClick={(e) => {
                  e.stopPropagation();
                  app.removeConversation(c.id);
                }}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="side-section options">
        <div className="side-label">ቅንብሮች</div>

        <button
          className={`tool-toggle${app.speakReplies ? ' on' : ''}`}
          style={{ width: '100%' }}
          onClick={() => app.setSpeakReplies(!app.speakReplies)}
          type="button"
        >
          <span className="dot" /> 🔊 መልስ ይናገር
        </button>

        <label className="side-field">
          <span>የንግግር ቋንቋ</span>
          <select
            className="mode-select"
            value={app.langMode}
            onChange={(e) => app.setLangMode(e.target.value as 'auto' | 'am' | 'en')}
          >
            <option value="auto">🌐 ራሱ ይለይ</option>
            <option value="am">አማርኛ</option>
            <option value="en">English</option>
          </select>
        </label>

        <button className="tool-toggle" style={{ width: '100%' }} onClick={() => setShowVoice((v) => !v)} type="button">
          <span className="dot" /> 🎛 የድምጽ ቅንብር {showVoice ? '▴' : '▾'}
        </button>
        {showVoice && (
          <VoicePanel
            voices={voices}
            prefs={app.prefs}
            onChange={app.setPrefs}
            onTest={testVoice}
            onReset={() => app.setPrefs({ ...DEFAULT_VOICE })}
          />
        )}
      </div>

      <div className="side-section side-bottom">
        <NavLink to="/review" className="nav-link" onClick={onNavigate}>
          🌱 ትርጉም አስተምር
        </NavLink>
      </div>

      <AuthDialog open={authOpen} onClose={() => setAuthOpen(false)} />
    </aside>
  );
}
