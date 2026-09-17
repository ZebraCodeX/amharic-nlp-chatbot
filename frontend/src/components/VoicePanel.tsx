import type { VoicesResponse } from '../api/types';
import type { VoicePrefs } from '../lib/voice';

interface Props {
  voices: VoicesResponse | null;
  prefs: VoicePrefs;
  onChange: (next: VoicePrefs) => void;
  onTest: () => void;
  onReset: () => void;
}

function Options({ voices, lang, value }: { voices: VoicesResponse | null; lang: string; value: string }) {
  const list = (voices?.voices || []).filter((v) => v.lang === lang);
  const extra = value && !list.some((v) => v.value === value);
  return (
    <>
      {extra && <option value={value}>{value}</option>}
      {list.map((v) => (
        <option key={v.value} value={v.value}>
          {v.label}
        </option>
      ))}
    </>
  );
}

export function VoicePanel({ voices, prefs, onChange, onTest, onReset }: Props) {
  const set = (patch: Partial<VoicePrefs>) => onChange({ ...prefs, ...patch });
  const ranges = voices?.ranges || {};
  const rate = (ranges.rate as [number, number]) || [80, 300];
  const pitch = (ranges.pitch as [number, number]) || [0, 99];
  const volume = (ranges.volume as [number, number]) || [0, 200];

  return (
    <div className="voice-panel card">
      <div className="voice-panel-head">
        <b>🎛 የድምጽ ቅንብር · Voice</b>
        <span className="badge">{voices?.engine || '…'}</span>
      </div>

      <label className="vp-row">
        <span>የአማርኛ ድምጽ</span>
        <select value={prefs.voiceAm} onChange={(e) => set({ voiceAm: e.target.value })}>
          <Options voices={voices} lang="am" value={prefs.voiceAm} />
        </select>
      </label>

      <label className="vp-row">
        <span>English voice</span>
        <select value={prefs.voiceEn} onChange={(e) => set({ voiceEn: e.target.value })}>
          <Options voices={voices} lang="en" value={prefs.voiceEn} />
        </select>
      </label>

      <label className="vp-row">
        <span>ፍጥነት · speed</span>
        <input
          type="range"
          min={rate[0]}
          max={rate[1]}
          value={prefs.rate}
          onChange={(e) => set({ rate: Number(e.target.value) })}
        />
        <em>{prefs.rate}</em>
      </label>

      <label className="vp-row">
        <span>ከፍታ · pitch</span>
        <input
          type="range"
          min={pitch[0]}
          max={pitch[1]}
          value={prefs.pitch}
          onChange={(e) => set({ pitch: Number(e.target.value) })}
        />
        <em>{prefs.pitch}</em>
      </label>

      <label className="vp-row">
        <span>ድምጽ መጠን · volume</span>
        <input
          type="range"
          min={volume[0]}
          max={volume[1]}
          value={prefs.volume}
          onChange={(e) => set({ volume: Number(e.target.value) })}
        />
        <em>{prefs.volume}</em>
      </label>

      <div className="vp-actions">
        <button className="btn btn-sm btn-primary" type="button" onClick={onTest}>
          ▶ ፈትን
        </button>
        <button className="btn btn-sm" type="button" onClick={onReset}>
          ↺ ነባሪ
        </button>
      </div>
    </div>
  );
}
