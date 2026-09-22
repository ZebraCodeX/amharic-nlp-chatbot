#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
grounding.py — answer from Zer's OWN knowledge, fully offline.

The embedded model is small, so instead of trusting it to recall facts the
assistant looks them up in its local data first and hands the model a short,
bounded context:

  * data/facts.json          — curated fact → answer (am + en)
  * data/rich_answers.json   — deep topic answers (Amharic)
  * data/knowledge_base.json — intents → responses

Everything here is local and pure-stdlib: no network, no external service, no
API key. `zer.py` / `llm.py` call `context()` before generating, so a 1.5B
model can still give a correct, sourced answer about its own domain.

    import grounding
    grounding.context('what is the speed of light', 'en')
    # -> "Use these facts ...\\n- The speed of light in a vacuum is ..."
"""

import json
import os
import re

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(REPO_ROOT, 'data')

_ETHIOPIC = re.compile(r'[\u1200-\u137f]+')
_LATIN = re.compile(r"[a-z0-9']+")
_WS = re.compile(r'\s+')

# Very common words carry no retrieval signal.
_STOP = {
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'of', 'to', 'in', 'on',
    'for', 'and', 'or', 'what', 'who', 'how', 'why', 'when', 'where', 'which',
    'tell', 'me', 'about', 'explain', 'do', 'does', 'did', 'can', 'you', 'i',
    'it', 'this', 'that', 'my', 'your', 'with', 'as', 'at', 'by', 'from',
    'ነው', 'ናቸው', 'ምን', 'ማለት', 'ስለ', 'እና', 'ወደ', 'በ', 'ከ', 'ለ', 'ይህ', 'ያ',
}

_index = None


def _tokens(text):
    text = (text or '').lower()
    toks = set(_ETHIOPIC.findall(text)) | set(_LATIN.findall(text))
    return {t for t in toks if t not in _STOP and len(t) > 1}


def _load_json(name, default):
    try:
        with open(os.path.join(DATA_DIR, name), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _rich_answer(entry):
    parts = [entry.get('summary') or '']
    points = [p for p in (entry.get('points') or []) if p]
    if points:
        parts.append('; '.join(points[:6]))
    return _WS.sub(' ', ' '.join(p for p in parts if p)).strip()


def _entries():
    """Flatten facts / rich answers / intents into retrievable entries."""
    global _index
    if _index is not None:
        return _index

    entries = []

    for fact in (_load_json('facts.json', {}) or {}).get('facts', []):
        pats = [p for p in (fact.get('am') or []) + (fact.get('en') or []) if p]
        if not pats:
            continue
        entries.append({'patterns': pats,
                        'am': fact.get('answer_am') or fact.get('answer_en'),
                        'en': fact.get('answer_en') or fact.get('answer_am')})

    kb = _load_json('knowledge_base.json', {}) or {}
    pats_by_tag = {i.get('tag'): (i.get('patterns') or [])
                   for i in kb.get('intents', [])}
    rich = (_load_json('rich_answers.json', {}) or {}).get('answers', {})
    for tag, entry in rich.items():
        answer = _rich_answer(entry or {})
        pats = pats_by_tag.get(tag) or [tag.replace('_', ' ')]
        if answer:
            entries.append({'patterns': pats, 'am': answer, 'en': None})

    kb_en = _load_json('knowledge_base_en.json', {}) or {}
    pats_by_tag_en = {i.get('tag'): (i.get('patterns') or [])
                      for i in kb_en.get('intents', [])}
    en_responses = {i.get('tag'): (i.get('responses') or [])
                    for i in kb_en.get('intents', [])}
    for tag, pats in pats_by_tag_en.items():
        responses = en_responses.get(tag) or []
        answer = responses[0] if responses else None
        if answer:
            entries.append({'patterns': pats, 'am': None, 'en': answer})

    # Sourced topic knowledge (Ethiopian history, Black history, logic, …),
    # compiled into data/knowledge_topics.json by tools/build_topic_kb.py.
    for topic in (_load_json('knowledge_topics.json', {}) or {}).get('topics', []):
        answer = topic.get('answer')
        pats = [p for p in (topic.get('patterns') or []) if p]
        if not answer or not pats:
            continue
        am = answer if topic.get('lang') == 'am' else None
        en = answer if topic.get('lang') != 'am' else None
        entries.append({'patterns': pats, 'am': am, 'en': en})

    _index = entries
    return entries


def _score(query, patterns):
    q = _tokens(query)
    if not q:
        return 0.0
    low = query.lower()
    best = 0.0
    for phrase in patterns:
        toks = _tokens(phrase)
        if not toks:
            continue
        overlap = len(q & toks)
        phrase_in = phrase.lower() in low
        # A single shared word (e.g. "rain") is too weak to ground on: require
        # two overlapping content words, or the whole multi-word phrase.
        if overlap < 2 and not (phrase_in and len(toks) >= 2):
            continue
        s = overlap / (len(toks) ** 0.5)
        if phrase_in and len(toks) >= 2:
            s += 1.5
        best = max(best, s)
    return best


def retrieve(text, lang='am', limit=3, min_score=0.6):
    """Return up to ``limit`` local answers relevant to ``text`` for ``lang``."""
    if not text:
        return []
    key = 'en' if str(lang or '').lower().startswith('en') else 'am'
    ranked = []
    for entry in _entries():
        answer = entry.get(key)
        if not answer:
            continue
        s = _score(text, entry['patterns'])
        if s >= min_score:
            ranked.append((s, answer))
    ranked.sort(key=lambda kv: kv[0], reverse=True)
    out, seen = [], set()
    for _s, answer in ranked:
        norm = answer.strip()
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
        if len(out) >= limit:
            break
    return out


def context(text, lang='am', limit=3, min_score=0.6, max_chars=1600):
    """A short, model-ready context block, or '' when nothing matches.

    ``max_chars`` bounds the injected text so it cannot crowd out the actual
    conversation in a small model's context window.
    """
    facts = retrieve(text, lang=lang, limit=limit, min_score=min_score)
    if not facts:
        return ''
    head = ('Use these facts from your own knowledge base — they are correct, '
            'so prefer them and do not contradict them:') if \
        str(lang or '').lower().startswith('en') else \
        ('ከራስህ የእውቀት መረጃ እነዚህ እውነታዎች አሉ — ትክክል ናቸው፤ እነሱን ተጠቀም፣ አትቃረን፦')
    chosen, budget = [], max_chars - len(head) - 1
    for fact in facts:
        fact = fact.strip()
        if not fact or budget <= 40:
            break
        if len(fact) > budget:
            cut = fact[:budget].rfind('. ')
            fact = fact[:cut + 1] if cut > 80 else fact[:budget]
        chosen.append(fact)
        budget -= len(fact)
    if not chosen:
        return ''
    body = '\n'.join(f'- {f}' for f in chosen)
    return f'{head}\n{body}'


def clear_cache():
    """Forget the built index (used by tests / after data edits)."""
    global _index
    _index = None
