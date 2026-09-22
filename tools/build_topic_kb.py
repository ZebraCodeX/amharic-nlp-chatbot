#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_topic_kb.py — turn the sourced topic set into runtime knowledge.

Reads ``training/data/topics_sft.jsonl`` (written by ``tools/fetch_topics.py``)
and writes ``data/knowledge_topics.json``, which ``grounding.py`` indexes so the
offline model can answer history / logic / philosophy questions from local data
with no network call.

    python3 tools/build_topic_kb.py
    python3 tools/build_topic_kb.py --in training/data/topics_sft.jsonl

Text is Wikipedia (CC BY-SA 4.0); the source list stays in
``training/data/topics_manifest.json``. Pure stdlib.
"""
import argparse
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IN = os.path.join(ROOT, 'training', 'data', 'topics_sft.jsonl')
DEFAULT_OUT = os.path.join(ROOT, 'data', 'knowledge_topics.json')

_ETHIOPIC = re.compile(r'[\u1200-\u137f]')
_WS = re.compile(r'\s+')

_EN_LEAD = re.compile(
    r'^(?:what|who|why|how|when|where|which)\b[\w\s]*?\b(?:is|are|was|were|'
    r'did|does|do|has|have)\b\s*', re.I)
_EN_LEAD2 = re.compile(r'^(?:explain|describe|tell\s+me\s+about|give\s+an?\s+'
                       r'overview\s+of|summari[sz]e)\s+', re.I)
_AM_LEAD = re.compile(r'^ስለ\s+')
_AM_TAIL = re.compile(r'\s*(?:አብራራልኝ|ንገረኝ|ምንድን\s*ነው|ማን\s*ነው|ምን\s*ነው)[፧?።.\s]*$')


def _key(question):
    """Derive a short, matchable key (usually the article title) from a question."""
    q = _WS.sub(' ', (question or '').strip())
    for side in (' ?', '?', '፧', '።', '.'):
        q = q.strip()
        if q.endswith(side.strip()):
            q = q[:-len(side.strip())].strip() if side.strip() else q
    out = _EN_LEAD.sub('', q)
    if out == q:
        out = _EN_LEAD2.sub('', q)
    out = _AM_LEAD.sub('', out)
    out = _AM_TAIL.sub('', out)
    out = out.strip(' .,:;?!?፧።')
    return out or q


def _clean_answer(answer, max_chars):
    text = re.sub(r'\[\d+\]', '', answer or '')
    text = _WS.sub(' ', text).strip()
    if len(text) > max_chars:
        text = text[:max_chars]
        cut = text.rfind('. ')
        text = text[:cut + 1] if cut > 120 else text
    return text


def build(src, max_chars):
    topics, seen = [], set()
    with open(src, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msgs = json.loads(line).get('messages') or []
            except ValueError:
                continue
            user = next((m.get('content') for m in msgs
                         if m.get('role') == 'user'), '')
            answer = next((m.get('content') for m in msgs
                           if m.get('role') == 'assistant'), '')
            user, answer = (user or '').strip(), _clean_answer(answer, max_chars)
            if not user or not answer:
                continue
            norm = user.lower()
            if norm in seen:
                continue
            seen.add(norm)
            lang = 'am' if _ETHIOPIC.search(user) else 'en'
            key = _key(user)
            patterns = [p for p in {user, key, key.lower()} if p and len(p) > 1]
            topics.append({'id': key[:64], 'lang': lang,
                           'question': user, 'answer': answer,
                           'patterns': patterns})
    return topics


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--in', dest='src', default=DEFAULT_IN)
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--max-chars', type=int, default=900)
    args = ap.parse_args()

    if not os.path.exists(args.src):
        raise SystemExit(f'input not found: {args.src} — run tools/fetch_topics.py')

    topics = build(args.src, args.max_chars)
    out = {'_meta': {'license': 'CC BY-SA 4.0 (Wikipedia)',
                     'source': 'training/data/topics_manifest.json',
                     'count': len(topics)},
           'topics': topics}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    langs = {'am': sum(t['lang'] == 'am' for t in topics),
             'en': sum(t['lang'] == 'en' for t in topics)}
    print(f'→ {len(topics)} topics ({langs}) → {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
