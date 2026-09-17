# -*- coding: utf-8 -*-
"""
amharic_nlp — a standalone, pure-Python NLP application for Amharic (Ge'ez).

This package is the *separated* NLP layer: it owns its own raw corpora
(`amharic_nlp/corpora/`), its training pipeline (`amharic_nlp/training.py`,
`amharic_nlp/tools/download_corpora.py`) and produces the learned artifacts in
the repo `data/` directory (nl_model.json, amharic_words.json, vocabulary.txt,
sentences.json, corpus_stats.json). The chatbot only talks to it through the
public API exposed here — it does not import module internals.

Public API mirrors the previous flat modules so existing imports keep working:
    from amharic_nlp import (AmharicNormalizer, AmharicTokenizer, NLModel, ...)

Components
----------
toolkit      pure text-processing primitives (normalizer, tokenizer, stemmer,
             stop words, sentence splitter, TF-IDF, document index, Bible corpus)
model        n-gram language model (NLModel) trained over the whole corpus
corpus       stream readers for many free-text formats (plaintext, Leipzig,
             Amharic Wikipedia dump XML, CC-100, amharic-bible-json)
training     end-to-end pipeline: corpora -> nl_model.json + amharic_words.json
             + vocabulary.txt + sentences.json + corpus_stats.json
suggester    type-ahead: closest words, next-word hints, sentence completion
tools        download_corpora.py (fetch free sources: Leipzig, Wikipedia, CC-100)

Pure stdlib. No dependencies. Fully offline once corpora are present.
"""

import os

from .toolkit import (
    AmharicNormalizer,
    AmharicTokenizer,
    AmharicStemmer,
    StopWordFilter,
    SentenceSplitter,
    TfidfVectorizer,
    DocumentIndex,
    BibleCorpus,
    AmharicTextProcessor,
    NORMALIZATION,
    ETHIOPIC_RE,
    DEFAULT_STOPWORDS,
    STEM_PREFIXES,
    STEM_SUFFIXES_CLEAN,
)
from .model import (
    NLModel,
    tokenize,
    tokenize as tokenize_words,
    build_from_sentences,
    build as build_ngram_model,
    DATA_DIR as _MODEL_DATA_DIR,
    MODEL_PATH,
)

__version__ = '2.0.0'

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(PACKAGE_DIR)
DATA_DIR = os.path.join(REPO_ROOT, 'data')          # merged learner artifacts
CORPORA_DIR = os.path.join(PACKAGE_DIR, 'corpora')  # raw inbound corpora


def data_path(name):
    """Absolute path of a processed artifact inside the repo data/ directory."""
    return os.path.join(DATA_DIR, name)


def corpora_path(domain=''):
    """Absolute corpus path; domain ∈ {'books','movies','articles','other'}."""
    return os.path.join(CORPORA_DIR, domain) if domain else CORPORA_DIR


# Late imports (keep construction cheap / optional features lazy).
from .suggester import Suggester   # noqa: E402, F401

__all__ = [
    'AmharicNormalizer', 'AmharicTokenizer', 'AmharicStemmer',
    'StopWordFilter', 'SentenceSplitter', 'TfidfVectorizer',
    'DocumentIndex', 'BibleCorpus', 'AmharicTextProcessor',
    'NLModel', 'Suggester', 'training', 'corpus',
    'NORMALIZATION', 'ETHIOPIC_RE', 'DEFAULT_STOPWORDS',
    'STEM_PREFIXES', 'STEM_SUFFIXES_CLEAN',
    'tokenize', 'tokenize_words', 'build_from_sentences', 'build_ngram_model',
    'DATA_DIR', 'CORPORA_DIR', 'MODEL_PATH', 'PACKAGE_DIR', 'REPO_ROOT',
    'data_path', 'corpora_path',
]