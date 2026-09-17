#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
suggester.py — type-ahead engine over the trained Amharic NLP artifacts.

Powers the chat/keyboard UI (`/api/suggest`): given a partial input it returns

    words      closest dictionary words matching the typed prefix
    next       highest-scoring next words (n-gram model continuations)
    sentences  corpus sentence completions starting with the input

All lookups are server-side and folded (ትንሽ/ትንሸ homophones collapse), so a
typo on the consonant row still matches. Pure stdlib.
"""

import json
import os

from . import DATA_DIR
from .toolkit import AmharicNormalizer
from .model import NLModel, MODEL_PATH

WORDS_PATH = os.path.join(DATA_DIR, 'amharic_words.json')
SENTENCES_PATH = os.path.join(DATA_DIR, 'sentences.json')
TOP_SENTENCES = 60000          # how many sentence-bank entries are scanned
PREFIX_MIN = 1                 # minimum prefix length to suggest words


class Suggester:
    """Loads the learned artifacts once and answers type-ahead queries."""

    def __init__(self, model_path=MODEL_PATH, words_path=WORDS_PATH,
                 sentences_path=SENTENCES_PATH):
        self.model = NLModel(model_path)
        self.normalizer = AmharicNormalizer()
        self._fold_cache = {}
        self._words = None       # [(w, f), ...] folded-deduplicated, desc freq
        self._sentences = None   # [(t, f), ...] folded sentence -> freq

    # -- loading ------------------------------------------------------------
    def _load_words(self):
        if self._words is not None:
            return
        words = []
        try:
            with open(WORDS_PATH, encoding='utf-8') as f:
                data = json.load(f)
            words = [(w['w'], w['f']) for w in data.get('words', [])]
        except (OSError, ValueError, TypeError):
            # fall back to the unigram model vocabulary
            uni = (self.model.load() or {}).get('unigram', {})
            words = list(uni.items())
        self._words = words

    def _load_sentences(self):
        if self._sentences is not None:
            return
        bank = []
        try:
            with open(SENTENCES_PATH, encoding='utf-8') as f:
                data = json.load(f)
            bank = [(s['t'], s['f']) for s in data.get('sentences', [])[:TOP_SENTENCES]]
        except (OSError, ValueError, TypeError):
            bank = []
        self._sentences = bank

    def _fold(self, s):
        key = s
        cached = self._fold_cache.get(key)
        if cached is not None:
            return cached
        out = self.normalizer.normalize(s.lower())
        self._fold_cache[key] = out
        return out

    # -- queries ------------------------------------------------------------
    def suggest(self, partial, k_words=8, k_next=4, k_sent=3):
        """:return {"words": [[w,f],...], "next": [[w,s],...], "sentences": [t,...]}"""
        raw = (partial or '').strip()
        fold = self._fold(raw)
        toks = [t for t in fold.split() if t]

        words = self._closest_words(toks[-1] if toks else '', k_words)
        next_ = self._next_words(toks, k_next)
        sentences = self._sentences_for(fold, k_sent)

        return {
            'words': words,
            'next': next_,
            'sentences': sentences,
        }

    def _closest_words(self, prefix, k=8):
        if len(prefix) < PREFIX_MIN:
            return []
        self._load_words()
        out = []
        seen = set()
        for w, f in self._words:
            if len(out) >= k:
                break
            if w.startswith(prefix) and w not in seen:
                seen.add(w)
                out.append([w, f])
        return out

    def _next_words(self, toks, k=4):
        if not toks:
            return self.model.starters(k)
        self.model.load()
        prev = tuple(toks[-2:])
        return [[w, c] for w, c in self.model.next_words(prev, k=k)]

    def _sentences_for(self, folded_prefix, k=3):
        if not folded_prefix or len(folded_prefix) < 2:
            return []
        self._load_sentences()
        if not self._sentences:
            return []
        out = []
        for t, f in self._sentences:
            if len(out) >= k:
                break
            if self._fold(t).startswith(folded_prefix):
                out.append(t)
        return out