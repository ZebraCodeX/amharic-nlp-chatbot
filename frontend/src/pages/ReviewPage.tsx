import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { ReviewItem, ReviewStats } from '../api/types';

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

export function ReviewPage() {
  const [stats, setStats] = useState<ReviewStats | null>(null);
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState('review');
  const [query, setQuery] = useState('');
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
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

  const load = useCallback(
    (reset: boolean, nextStatus = status, nextQuery = query) => {
      setLoading(true);
      const nextOffset = reset ? 0 : offset;
      api
        .translations({ status: nextStatus, q: nextQuery, limit: LIMIT, offset: nextOffset })
        .then((d) => {
          setTotal(d.total);
          setOffset(nextOffset + d.items.length);
          setItems((prev) => (reset ? d.items : [...prev, ...d.items]));
        })
        .catch(() => showToast('ስህተት። እንደገና ሞክር።', false))
        .finally(() => setLoading(false));
    },
    [offset, status, query, showToast],
  );

  useEffect(() => {
    loadStats();
    load(true, 'review', '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const t = window.setTimeout(() => load(true, status, query), 250);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, status]);

  return (
    <div className="wrap">
      <span className="eyebrow">አማርኛ ⇄ English</span>
      <h1 className="section-title">የትርጉም ማስተካከያ</h1>
      <p className="lede">
        ዝቅተኛ እምነት (ከ90% በታች) ያላቸውን ትርጉሞች እዚህ አስተካክል። እያንዳንዱ ማስተካከያ የመላውን መተግበሪያ
        ትርጉም ወዲያውኑ ያሻሽላል።
      </p>

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
            <span>ያልተተረጎሙ</span>
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
      </div>

      <div className="review-list">
        {items.map((it) => (
          <ReviewRow
            key={`${it.am}-${it.status}`}
            item={it}
            status={status}
            onSaved={(updated, resolved) => {
              if (resolved) {
                setTimeout(
                  () => setItems((prev) => prev.filter((p) => p.am !== updated.am)),
                  700,
                );
              }
              loadStats();
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
  onSaved: (item: ReviewItem, resolved: boolean) => void;
  onToast: (msg: string, ok: boolean) => void;
}

function ReviewRow({ item, status, onSaved, onToast }: RowProps) {
  const [value, setValue] = useState(item.en);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  const meta = STATUS_META[item.status] ?? STATUS_META.suggested;
  const pct = Math.round((item.confidence || 0) * 100);

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
      onToast('✓ ተቀምጧል — ትርጉሙ ተሻሽሏል', true);
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
      <div className="review-am">{item.am}</div>
      <div className="review-mid">
        <input
          className="review-input"
          value={value}
          placeholder="English translation…"
          dir="ltr"
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') save(false);
          }}
        />
        <div className="conf-track">
          <div
            className={`conf-fill${item.confidence >= THRESHOLD ? ' ok' : ''}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="badges">
          <span className={`badge ${meta.cls}`}>{meta.label}</span>
          <span className="badge">እምነት {pct}%</span>
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
