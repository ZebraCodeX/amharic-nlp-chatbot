import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { api } from '../api/client';
import type { LlmStatus } from '../api/types';
import { useInstallPrompt } from '../hooks/useInstallPrompt';

export function AppShell() {
  const [llm, setLlm] = useState<LlmStatus | null>(null);
  const { canInstall, install } = useInstallPrompt();
  const location = useLocation();
  const onReview = location.pathname.startsWith('/review');

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

        {onReview ? (
          // The review page is a pure translation-teaching surface: no chat
          // chrome, just a way back to the assistant.
          <nav className="nav">
            <NavLink to="/" className="nav-link">
              ← ወደ ውይይት
            </NavLink>
          </nav>
        ) : (
          <nav className="nav">
            {canInstall && (
              <button className="btn btn-gold btn-sm" onClick={install} title="Install this app">
                ⬇ ጫን
              </button>
            )}
            <span className={`status-pill${llm?.available ? ' on' : ''}`} title="LLM brain status">
              <span className="dot" />
              {llm?.available ? `✦ ${llm.model || 'AI አእምሮ'}` : 'offline AI'}
            </span>
            <NavLink
              to="/review"
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            >
              ትርጉም አስተምር
            </NavLink>
          </nav>
        )}
      </header>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
