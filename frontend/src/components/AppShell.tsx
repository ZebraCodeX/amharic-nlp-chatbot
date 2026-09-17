import { useEffect, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { api } from '../api/client';
import type { LlmStatus } from '../api/types';
import { useInstallPrompt } from '../hooks/useInstallPrompt';

// One page (chat) + Review. Voice and the Amharic keyboard live inside the chat.
const LINKS = [{ to: '/review', label: 'ትርጉም' }];

export function AppShell() {
  const [llm, setLlm] = useState<LlmStatus | null>(null);
  const { canInstall, install } = useInstallPrompt();

  useEffect(() => {
    api.llmStatus().then(setLlm).catch(() => setLlm(null));
  }, []);

  return (
    <div className="app-shell">
      <header className="topbar">
        <NavLink to="/" className="brand" style={{ textDecoration: 'none' }}>
          <span className="brand-mark">ዘ</span>
          <span className="brand-text">
            <b>ዘር</b>
            <span>Zer · Amharic AI</span>
          </span>
        </NavLink>

        <nav className="nav">
          {LINKS.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            >
              {l.label}
            </NavLink>
          ))}
        </nav>

        {canInstall && (
          <button className="btn btn-gold btn-sm" onClick={install} title="Install this app">
            ⬇ ጫን
          </button>
        )}

        <span className={`status-pill${llm?.available ? ' on' : ''}`} title="LLM brain status">
          <span className="dot" />
          {llm?.available ? `✦ ${llm.model || 'AI አእምሮ'}` : 'offline AI'}
        </span>
      </header>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
