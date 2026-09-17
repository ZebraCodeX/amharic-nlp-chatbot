import { useEffect, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { api } from '../api/client';
import type { LlmStatus } from '../api/types';

const LINKS = [
  { to: '/', label: 'ውይይት', end: true },
  { to: '/keyboard', label: 'ኪቦርድ' },
  { to: '/review', label: 'ትርጉም' },
];

export function AppShell() {
  const [llm, setLlm] = useState<LlmStatus | null>(null);

  useEffect(() => {
    api.llmStatus().then(setLlm).catch(() => setLlm(null));
  }, []);

  return (
    <div className="app-shell">
      <header className="topbar">
        <NavLink to="/" className="brand" style={{ textDecoration: 'none' }}>
          <span className="brand-mark">ሕ</span>
          <span className="brand-text">
            <b>ሕሳር</b>
            <span>Amharic AI</span>
          </span>
        </NavLink>

        <nav className="nav">
          {LINKS.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            >
              {l.label}
            </NavLink>
          ))}
        </nav>

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
