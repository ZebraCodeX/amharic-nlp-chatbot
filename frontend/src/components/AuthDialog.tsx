import { useState } from 'react';
import { useApp } from '../app/AppContext';

export function AuthDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { login, register } = useApp();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!open) return null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const name = username.trim();
    if (name.length < 3) {
      setError('የተጠቃሚ ስም ቢያንስ 3 ፊደል ይሁን። / username must be at least 3 characters');
      return;
    }
    if (mode === 'register' && password.length < 6) {
      setError('የይለፍ ቃል ቢያንስ 6 ፊደል ይሁን። / password must be at least 6 characters');
      return;
    }
    setBusy(true);
    try {
      if (mode === 'login') await login(name, password);
      else await register({ username: name, password, display_name: displayName.trim() });
      onClose();
    } catch (err) {
      setError((err as Error).message || 'አልተሳካም። እንደገና ሞክር። / failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal card" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3 className="section-title" style={{ fontSize: '1.4rem' }}>
          {mode === 'login' ? 'ግባ · Sign in' : 'ተመዝገብ · Create account'}
        </h3>
        <p className="lede" style={{ fontSize: '0.86rem', marginBottom: 14 }}>
          ውይይቶችህንና ትምህርቶችህን ለማስታወስ መለያ ይክፈት።
        </p>

        <input
          className="review-input"
          placeholder="የተጠቃሚ ስም / username"
          value={username}
          autoCapitalize="none"
          onChange={(e) => setUsername(e.target.value)}
        />
        {mode === 'register' && (
          <input
            className="review-input"
            placeholder="ስም / display name (optional)"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
        )}
        <input
          className="review-input"
          type="password"
          placeholder="የይለፍ ቃል / password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        {error && <div className="voice-error">{error}</div>}

        <button className="btn btn-primary" type="submit" disabled={busy || !username || !password}>
          {busy ? '…' : mode === 'login' ? 'ግባ' : 'ተመዝገብ'}
        </button>
        <button
          className="link-btn"
          type="button"
          onClick={() => {
            setMode(mode === 'login' ? 'register' : 'login');
            setError(null);
          }}
        >
          {mode === 'login' ? 'አዲስ መለያ ክፈት' : 'ቀድሞ መለያ አለኝ'}
        </button>
      </form>
    </div>
  );
}
