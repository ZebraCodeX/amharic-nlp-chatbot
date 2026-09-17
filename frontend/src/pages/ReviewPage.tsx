import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { LetterCount, ReviewItem, ReviewStats } from '../api/types';

const TABS = [
  { key: 'review', label: 'እምነት <90%' },
  { key: 'untranslated', label: 'ያልተተረጎሙ' },
  { key: 'verified', label: 'የተረጋገጡ/የተስተካከሉ' },
];
const LIMIT = 50;
const THRESHOLD = 0.9;

const STATUS_META: Record<string, { label: string; cls: string }> = {
  suggested: { label: 'ማረጋገጫ ይፈልጋል', cls: 'to-review' },
  verified: { label: '✓ የተረጋገጠ', cls: 'verified' },
  corrected: { label: '✎ የተስተካከለ', cls: 'corrected' },
  untranslated: { label: 'ትርጉም የለውም', cls: 'none' },
};

/* --- limited-concurrency English suggestions (server caches each result) --- */
const suggestionCache = new Map<string, string>();
let activeSuggestions = 0;
const suggestQueue: (() => void)[] = [];

async function fetchSuggestion(word: string): Promise<string> {
  if (suggestionCache.has(word)) return suggestionCache.get(word) as string;
  const run = async () => {
    const res = await api.translate(word, 'en');
    const text = (res.translated || '').trim();
    suggestionCache.set(word, text);
    return text;
  };
  return new Promise<string>((resolve, reject) => {
    const start = () => {
      activeSuggestions += 1;
      run()
        .then(resolve, reject)
        .finally(() => {
          activeSuggestions -= 1;
          const next = suggestQueue.shift();
          if (next) next();
        });
    };
    if (activeSuggestions < 3) start();
    else suggestQueue.push(start);
  });
}

export function ReviewPage() {
  const [stats, setStats] = useState<ReviewStats | null>(null);
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState('review');
  const [letter, setLetter] = useState('');
  const [letters, setLetters] = useState<LetterCount[]>([]);
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [suggestOn, setSuggestOn] = useState(true);
  const [learned, setLearned] = useState(0);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const toastTimer = useRef<number | undefined>(undefined);

  const showToast = useCallback((msg: string, ok: boolean) => {
    setToast({ msg, ok });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 3000);
  }, []);

  const loadStats = useCallback(() => {
    api.reviewStats().then(setStats).catch(() => {});
  }, []);

  const loadLetters = useCallback(() => {
    api.translationLetters().then((d) => setLetters(d.letters)).catch(() => {});
  }, []);

  const loadLearning = useCallback(() => {
    api.learningStats().then((d) => setLearned(d.learned)).catch(() => {});
  }, []);

  const load = useCallback(
    (reset: boolean, nextStatus = status, nextQuery = query, nextLetter = letter) => {
      setLoading(true);
      const nextOffset = reset ? 0 : offset;
      api
        .translations({
          status: nextStatus,
          q: nextQuery,
          letter: nextLetter || undefined,
          limit: LIMIT,
          offset: nextOffset,
        })
        .then((d) => {
          setTotal(d.total);
          setOffset(nextOffset + d.items.length);
          setItems((prev) => (reset ? d.items : [...prev, ...d.items]));
        })
        .catch(() => showToast('ስህተት። እንደገና ሞክር።', false))
        .finally(() => setLoading(false));
    },
    [offset, status, query, letter, showToast],
  );

  useEffect(() => {
    loadStats();
    loadLetters();
    loadLearning();
    load(true, 'review', '', '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const t = window.setTimeout(() => load(true, status, query, letter), 250);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, status, letter]);

  return (
    <div className="wrap">
      <span className="eyebrow">ዘርን አስተምር · Teach Zer</span>
      <h1 className="section-title">የትርጉም ማስተማሪያ</h1>
      <p className="lede">
        ለእያንዳንዱ ቃል ትክክለኛውን የእንግሊዝኛ ትርጉም አስተምር — ✓ (ትክክል) ወይም ✎ (አስተካክል)።
        ዘር ከእነዚህ ትምህርቶች ተምሮ በሚመልሳቸው መልሶች ይጠቀማቸዋል።
      </p>

      <div className="learn-banner">
        🌱 ዘር <b>{learned}</b> የትርጉም ትምህርቶችን ተምሯል — እያንዳንዱ ማስተካከያ መልሱን ያሻሽላል።
      </div>

      {stats && (
        <div className="stat-grid">
          <div className="stat-card">
            <b>{stats.total}</b>
            <span>ጠቅላላ ቃላት</span>
          </div>
          <div className="stat-card gold">
            <b>{stats.low_confidence}</b>
            <span>እምነት &lt;90%</span>
          </div>
          <div className="stat-card terra">
            <b>{stats.untranslated}</b>
            <span>ትርጉም የለውም</span>
          </div>
          <div className="stat-card">
            <b>{stats.verified}</b>
            <span>የተረጋገጡ</span>
          </div>
          <div className="stat-card">
            <b>{stats.corrected}</b>
            <span>የተስተካከሉ</span>
          </div>
        </div>
      )}

      <div className="toolbar">
        <input
          className="search-input"
          placeholder="ቃል ፈልግ… (በአማርኛ ወይም English)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="tabbar">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={`tab${status === t.key ? ' active' : ''}`}
              onClick={() => setStatus(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <button
          className={`tool-toggle${suggestOn ? ' on' : ''}`}
          type="button"
          onClick={() => setSuggestOn((v) => !v)}
          title="Show an English translation for every word"
        >
          <span className="dot" /> 🌐 ትርጉም አሳይ
        </button>
      </div>

      {letters.length > 0 && (
        <div className="letterbar">
          <button
            className={`letter-chip${letter === '' ? ' active' : ''}`}
            onClick={() => setLetter('')}
          >
            ሁሉም
          </button>
          {letters.map((l) => (
            <button
              key={l.letter}
              className={`letter-chip${letter === l.letter ? ' active' : ''}`}
              onClick={() => setLetter(l.letter)}
              title={`${l.count} ቃላት`}
            >
              {l.letter}
              <small>{l.count}</small>
            </button>
          ))}
        </div>
      )}

      <div className="review-list">
        {items.map((it) => (
          <ReviewRow
            key={`${it.am}-${it.status}`}
            item={it}
            status={status}
            suggestOn={suggestOn}
            onSuggest={fetchSuggestion}
            onSaved={(_updated, resolved) => {
              if (resolved) {
                setTimeout(() => setItems((prev) => prev.filter((p) => p.am !== it.am)), 700);
              }
              loadStats();
              loadLetters();
              loadLearning();
            }}
            onToast={showToast}
          />
        ))}
        {!loading && items.length === 0 && <div className="empty">ምንም አልተገኘም።</div>}
        {loading && (
          <div className="spinner">
            <i />
          </div>
        )}
      </div>

      {offset < total && (
        <div style={{ textAlign: 'center', marginTop: 20 }}>
          <button className="btn btn-primary" disabled={loading} onClick={() => load(false)}>
            ተጨማሪ አሳይ ({offset}/{total})
          </button>
        </div>
      )}

      <div className={`toast${toast ? ' show' : ''}${toast && !toast.ok ? ' err' : ''}`}>
        {toast?.msg}
      </div>
    </div>
  );
}

interface RowProps {
  item: ReviewItem;
  status: string;
  suggestOn: boolean;
  onSuggest: (word: string) => Promise<string>;
  onSaved: (item: ReviewItem, resolved: boolean) => void;
  onToast: (msg: string, ok: boolean) => void;
}

function ReviewRow({ item, status, suggestOn, onSuggest, onSaved, onToast }: RowProps) {
  const [value, setValue] = useState(item.en);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [suggested, setSuggested] = useState(false);

  const meta = STATUS_META[item.status] ?? STATUS_META.suggested;
  const pct = Math.round((item.confidence || 0) * 100);

  const suggest = useCallback(async () => {
    setSuggesting(true);
    try {
      const text = await onSuggest(item.am);
      if (text) {
        setValue(text);
        setSuggested(true);
      } else {
        onToast('ትርጉም አልተገኘም — በእጅህ ጻፍ', false);
      }
    } catch {
      onToast('ትርጉም ማምጣት አልተቻለም', false);
    } finally {
      setSuggesting(false);
    }
  }, [item.am, onSuggest, onToast]);

  // Show an English translation to judge, even when none is stored yet.
  useEffect(() => {
    if (!suggestOn || item.en) return;
    let alive = true;
    (async () => {
      setSuggesting(true);
      try {
        const text = await onSuggest(item.am);
        if (alive && text) {
          setValue(text);
          setSuggested(true);
        }
      } catch {
        /* ignore */
      } finally {
        if (alive) setSuggesting(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [suggestOn, item.am, item.en, onSuggest]);

  async function save(isCorrection: boolean) {
    const v = value.trim();
    if (!v) {
      onToast('እባክህ ትርጉም ጻፍ', false);
      return;
    }
    setBusy(true);
    try {
      const res = await api.verify({ text: item.am, translation: item.en || v, correct: v });
      const newConf = isCorrection && v !== item.en ? 0.95 : 1.0;
      setValue(res.corrected || v);
      setSaved(true);
      onToast('✓ ተቀምጧል — ዘር ተምሯል', true);
      const resolved = status === 'review' && newConf >= THRESHOLD;
      onSaved({ ...item, en: res.corrected || v, confidence: newConf }, resolved);
    } catch {
      onToast('ተቀምጦ አልተቻለም', false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`review-row${saved ? ' saved' : ''}`}>
      <div className="review-am">
        {item.am}
        {item.letter && <small className="review-letter">{item.letter}</small>}
      </div>
      <div className="review-mid">
        <div className="en-row">
          <input
            className="review-input"
            value={value}
            placeholder={suggesting ? 'ትርጉም በመፈለግ ላይ…' : 'English translation…'}
            dir="ltr"
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') save(false);
            }}
          />
          <button
            className="btn btn-sm"
            onClick={suggest}
            disabled={suggesting}
            title="Fetch an English translation suggestion"
          >
            {suggesting ? '…' : '🌐'}
          </button>
        </div>
        <div className="conf-track">
          <div
            className={`conf-fill${item.confidence >= THRESHOLD ? ' ok' : ''}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="badges">
          <span className={`badge ${meta.cls}`}>{meta.label}</span>
          <span className="badge">እምነት {pct}%</span>
          {suggested && <span className="badge">🌐 የተጠቆመ</span>}
          {item.endorsed > 0 && <span className="badge">{item.endorsed}✓</span>}
        </div>
      </div>
      <div className="review-actions">
        <button className="btn btn-sm btn-primary" disabled={busy} onClick={() => save(false)}>
          ✓ ትክክል
        </button>
        <button className="btn btn-sm btn-gold" disabled={busy} onClick={() => save(true)}>
          ✎ አስቀምጥ
        </button>
      </div>
    </div>
  );
}
