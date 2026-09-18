import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { useOnline } from '../hooks/useOnline';
import { Sidebar } from './Sidebar';

export function AppShell() {
  const { online } = useOnline();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className={`app-layout${menuOpen ? ' menu-open' : ''}`}>
      <div className="mobile-bar">
        <button className="icon-btn" onClick={() => setMenuOpen((v) => !v)} aria-label="menu">
          ☰
        </button>
        <span className="mobile-brand">ዘር · Zer</span>
        <span className={`status-dot${online ? ' on' : ' off'}`} title={online ? 'online' : 'offline'} />
      </div>

      <div className="sidebar-wrap">
        <Sidebar onNavigate={() => setMenuOpen(false)} />
      </div>

      {menuOpen && <div className="scrim" onClick={() => setMenuOpen(false)} />}

      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
