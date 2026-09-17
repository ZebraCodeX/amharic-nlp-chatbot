#!/usr/bin/env python3
"""
model.py — Amharic n-gram language model (part of the standalone NLP app).

BUILD (whole corpus, books/movies/articles/other):
    python3 -m amharic_nlp.training --corpora amharic_nlp/corpora
    (or) python3 amharic_nlp/tools/train.py   -> thin wrapper

BUILD (legacy, Bible + knowledge base only):
    python3 -m amharic_nlp.model build /path/to/amharic_bible.json

RUNTIME:
    from amharic_nlp import NLModel
    model = NLModel()
    model.predict(prev=(w1, w2))   # top continuation words given the last 1-2 words
    model.starters()               # common sentence-opening words
    model.common_words(top)        # high-frequency vocabulary (for the dictionary)

Pure stdlib. No dependencies.
"""

import json
import os
import re
import sys
import collections

MODULE_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(MODULE_BASE, 'data')
MODEL_PATH = os.path.join(DATA_DIR, 'nl_model.json')

WORD_RE = re.compile(r'[\u1200-\u135a]+')
MAX_PREV_VOCAB = 24000    # predictors (prev words) kept, ordered by frequency
MIN_BIGRAM = 2            # drop rare bigrams
MIN_TRIGRAM = 2           # drop rare trigrams
MAX_UNI = 16000           # unigram words kept in the payload


def tokenize(text):
    return WORD_RE.findall(text or '')


def bible_verses(path):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    for book in data.get('books', []):
        for ch in book.get('chapters', []):
            for v in ch.get('verses', []):
                if isinstance(v, str) and v.strip():
                    yield v.strip()


def kb_sentences(path):
    with open(path, encoding='utf-8') as f:
        kb = json.load(f)
    for it in kb.get('intents', []):
        for p in it.get('patterns', []):
            yield p
        for r in it.get('responses', []):
            yield r


def build_from_sentences(sentences, out=MODEL_PATH, max_prev_vocab=MAX_PREV_VOCAB,
                         max_uni=MAX_UNI, min_bigram=MIN_BIGRAM,
                         min_trigram=MIN_TRIGRAM, starters=400):
    """Train unigram/bigram/trigram/starters from an iterable of sentences.

    Shared by the legacy `build()` entry point and the full corpus training
    pipeline (`amharic_nlp.training`). Larger corpora can raise the caps.
    """
    unigram = collections.Counter()
    bigram = collections.Counter()
    trigram = collections.Counter()
    starter_ctr = collections.Counter()

    n_sent = 0
    for s in sentences:
        if not s:
            continue
        toks = [t for t in tokenize(s) if len(t) >= 1]
        if len(toks) < 2:
            continue
        n_sent += 1
        if toks:
            starter_ctr[toks[0]] += 1
        unigram.update(toks)
        for w1, w2 in zip(toks, toks[1:]):
            bigram[(w1, w2)] += 1
        for w1, w2, w3 in zip(toks, toks[1:], toks[2:]):
            trigram[(w1, w2, w3)] += 1

    prev_vocab = {w for w, _ in unigram.most_common(max_prev_vocab)}

    uni = {w: c for w, c in unigram.most_common(max_uni) if len(w) <= 20}

    bi = {}
    for (a, b), c in bigram.items():
        if c >= min_bigram and a in prev_vocab:
            bi.setdefault(a, {})[b] = c

    tri = {}
    for (a, b, d), c in trigram.items():
        if c >= min_trigram and a in prev_vocab and b in prev_vocab:
            tri.setdefault(a + '|' + b, {})[d] = c

    payload = {
        'n_sentences': n_sent,
        'unigram': uni,
        'bigram': bi,
        'trigram': tri,
        'starters': dict(starter_ctr.most_common(starters)),
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    size = os.path.getsize(out) / 1024 / 1024
    print(f'built {out}: sentences={n_sent} unigram={len(uni)} '
          f'bigram_keys={len(bi)} trigram_keys={len(tri)} size={size:.2f} MB')
    return payload


def build(bible_path=None, out=MODEL_PATH):
    bible_path = bible_path or sys.argv[2] if len(sys.argv) > 2 else '/tmp/amharic_bible.json'
    kb_path = os.path.join(DATA_DIR, 'knowledge_base.json')

    sentences = []
    if os.path.exists(bible_path):
        sentences.extend(bible_verses(bible_path))
    if os.path.exists(kb_path):
        sentences.extend(kb_sentences(kb_path))
    if not sentences:
        raise SystemExit('No corpus found. Put the Amharic Bible at ' + bible_path)

    return build_from_sentences(sentences, out=out)


class NLModel:
    """Runtime reader + predictor over data/nl_model.json."""

    def __init__(self, path=MODEL_PATH):
        self.path = path
        self.data = None

    def load(self):
        if self.data is None and os.path.exists(self.path):
            with open(self.path, encoding='utf-8') as f:
                self.data = json.load(f)
        return self.data

    def next_words(self, prev, k=8, weight=1.0):
        """Given a tuple of the last 1-2 words, return [(word, score)] continuations."""
        data = self.load()
        if not data:
            return []
        prev = [''] + [w for w in prev if w][-2:]
        options = collections.Counter()
        if len(prev) >= 3 and prev[-2] and prev[-1]:
            pair = prev[-2] + '|' + prev[-1]
            for w, c in (data.get('trigram') or {}).get(pair, {}).items():
                options[w] += c * 3
        if prev[-1]:
            for w, c in (data.get('bigram') or {}).get(prev[-1], {}).items():
                options[w] += c * weight
        return options.most_common(k)

    def starters(self, k=8):
        data = self.load()
        return list((data or {}).get('starters', {}).items())[:k]

    def common_words(self, top=2500, min_len=2, max_len=20, exclude=()):
        data = self.load()
        exclude = set(exclude)
        out = []
        for w, c in (data or {}).get('unigram', {}).items():
            if min_len <= len(w) <= max_len and w not in exclude:
                out.append((w, c))
        return out[:top]


if __name__ == '__main__':
    build()