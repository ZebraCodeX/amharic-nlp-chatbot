#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
learning.py — Zer learns from the translations humans teach in /review.

Every correction saved by the review UI lands in the translator's correction
store. This module turns those verified/corrected pairs into a small *learned
glossary* and injects the relevant ones into

  * the LLM system prompt (so a connected model answers using them), and
  * the offline rule brain (direct "what does X mean / translate X" answers),

so teaching a translation visibly changes how Zer responds afterwards.
"""

import re

ETHIOPIC_RE = re.compile(r'[\u1200-\u137F]+')

# Phrasings that ask about a word's translation/meaning.
_ASKS_MEANING = re.compile(
    r'(ምን\s*ማለት|ትርጉም|በእንግሊዝኛ|in\s+english|translate|means?\b|how\s+do\s+you\s+say)',
    re.IGNORECASE)


def _corrections():
    """Snapshot of the translator's correction store."""
    import translator
    translator._load_corrections()
    with translator._CORR_LOCK:
        return [dict(r) for r in translator._CORR]


def learned_pairs():
    """{amharic: english} from human-verified/corrected am→en records."""
    out = {}
    for rec in _corrections():
        if rec.get('src') != 'am' or rec.get('dst') != 'en':
            continue
        am = (rec.get('text') or '').strip()
        en = (rec.get('corrected') or rec.get('original') or '').strip()
        if am and en:
            out[am] = en
    return out


def learned_for(text, limit=8):
    """Learned pairs relevant to ``text`` (the word appears in the message)."""
    text = text or ''
    pairs = learned_pairs()
    hits = []
    for am, en in pairs.items():
        if am in text:
            hits.append((am, en))
    if not hits:
        toks = [t for t in ETHIOPIC_RE.findall(text) if len(t) >= 2]
        for am, en in pairs.items():
            if any(t.startswith(am) or am.startswith(t) for t in toks):
                hits.append((am, en))
    return hits[:limit]


def recent(limit=6):
    """Most recently taught pairs (fallback context for the LLM)."""
    recs = [r for r in _corrections() if r.get('src') == 'am' and r.get('dst') == 'en']
    recs.sort(key=lambda r: r.get('created_ts', ''), reverse=True)
    out = []
    for r in recs[:limit]:
        am = (r.get('text') or '').strip()
        en = (r.get('corrected') or r.get('original') or '').strip()
        if am and en:
            out.append((am, en))
    return out


def hints(text, limit=8):
    """'am = en' lines to append to a system prompt (relevant, else recent)."""
    pairs = learned_for(text, limit) or recent(limit)
    return [f'{am} = {en}' for am, en in pairs]


def answer(text):
    """A direct answer from the learned glossary for a meaning/translation ask.

    Returns (reply, lang) or None. Only fires on translation-style questions so
    it never hijacks normal conversation.
    """
    text = text or ''
    if not _ASKS_MEANING.search(text):
        return None
    pairs = learned_for(text, limit=4)
    if not pairs:
        return None
    if re.search(r'[A-Za-z]', text) and not ETHIOPIC_RE.search(text):
        # English question about Amharic words
        body = '; '.join(f'{am} = {en}' for am, en in pairs)
        return (f'From what you taught me: {body}.', 'en')
    body = '\n'.join(f'• {am} — {en}' for am, en in pairs)
    return (f'ካስተማርከኝ ያውቃለሁ፦\n{body}', 'am')


def stats():
    pairs = learned_pairs()
    return {
        'learned': len(pairs),
        'recent': [{'am': am, 'en': en} for am, en in recent(5)],
    }
