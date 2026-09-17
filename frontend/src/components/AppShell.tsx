import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useInstallPrompt } from '../hooks/useInstallPrompt';
import { useOnline } from '../hooks/useOnline';

export function AppShell() {
  const { canInstall, install } = useInstallPrompt();
  const { online, llm } = useOnline();
  const location = useLocation();
  const onReview = location.pathname.startsWith('/review');

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
          // The review page is a pure translation-teaching surface: no chat chrome.
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
            <span
              className={`status-pill${online ? ' on' : ' off'}`}
              title={online ? 'Connected to Zer' : 'Offline — the installed app still works'}
            >
              <span className="dot" />
              {online ? 'በመስመር ላይ · online' : 'ከመስመር ውጭ · offline'}
            </span>
            {online && llm?.available && (
              <span className="brain-pill" title={`Generative model: ${llm.model || ''}`}>
                ✦ AI አእምሮ
              </span>
            )}
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
