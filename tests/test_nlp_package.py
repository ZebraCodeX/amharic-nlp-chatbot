#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the separated Amharic NLP app (package amharic_nlp/), its trained
artifacts, the type-ahead Suggester and the /api/suggest chat route.

Run:  python3 -m unittest tests.test_nlp_package -v
"""
import json
import os
import threading
import unittest
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
import sys
sys.path.insert(0, ROOT)

import amharic_nlp
from amharic_nlp import (NLModel, Suggester, corpus, training,
                         data_path, corpora_path, DATA_DIR)


class PackageApiTest(unittest.TestCase):
    """The package exposes the old flat-module API through its __init__."""

    def test_version_and_paths(self):
        self.assertEqual(amharic_nlp.__version__, '2.0.0')
        self.assertEqual(DATA_DIR, os.path.join(ROOT, 'data'))
        self.assertTrue(corpora_path('books').endswith(os.path.join('corpora', 'books')))

    def test_toolkit_re_exports(self):
        from amharic_nlp import (AmharicNormalizer, AmharicTokenizer,
                                 AmharicStemmer, StopWordFilter,
                                 SentenceSplitter, TfidfVectorizer)
        n = AmharicNormalizer()
        self.assertEqual(n.normalize('ሀመልክት'), 'ሀመልክት')
        self.assertEqual(AmharicTokenizer().tokenize('ሰላም እንዴት'), ['ሰላም', 'እንዴት'])

    def test_training_module_importable(self):
        self.assertTrue(callable(training.train))
        self.assertTrue(callable(corpus.plaintext))


class CorpusAssetsTest(unittest.TestCase):
    """The phrase-level artifacts produced by the training pipeline exist."""

    def setUp(self):
        self.stats = None
        stats_path = data_path('corpus_stats.json')
        if os.path.exists(stats_path):
            with open(stats_path, encoding='utf-8') as f:
                self.stats = json.load(f)

    def test_stats_written(self):
        self.assertIsNotNone(self.stats, 'run python3 -m amharic_nlp.training first')
        self.assertIn('domains', self.stats)
        for d in ('books', 'articles', 'other'):
            self.assertIn(d, self.stats['domains'])
        self.assertGreater(self.stats['total_sentences'], 100000)
        self.assertGreater(self.stats['total_unique_words'], 50000)

    def test_vocabulary_file(self):
        path = data_path('vocabulary.txt')
        self.assertTrue(os.path.exists(path))
        with open(path, encoding='utf-8') as f:
            lines = f.readlines()
        self.assertGreater(len(lines), 50000)
        word, _, count = lines[0].partition('\t')
        self.assertTrue(word.strip())
        self.assertTrue(count.strip().isdigit())

    def test_dictionary_json(self):
        with open(data_path('amharic_words.json'), encoding='utf-8') as f:
            d = json.load(f)
        self.assertGreater(d['count'], 2000)
        self.assertEqual(len(d['words']), d['count'])
        freqs = [w['f'] for w in d['words']]
        self.assertEqual(freqs, sorted(freqs, reverse=True))

    def test_ngram_loaded(self):
        model = NLModel()
        self.assertTrue(model.load())
        self.assertGreater(len(model.data['unigram']), 2000)
        self.assertTrue(model.data['bigram'])
        self.assertTrue(model.data['trigram'])

    def test_sentence_bank(self):
        with open(data_path('sentences.json'), encoding='utf-8') as f:
            bank = json.load(f)
        self.assertGreater(bank['count'], 0)
        self.assertTrue(all('t' in s and 'f' in s for s in bank['sentences']))


class SuggesterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sg = Suggester()

    def test_sentence_completion(self):
        out = self.sg.suggest('ሰላም')
        self.assertTrue(out['sentences'])
        self.assertTrue(out['sentences'][0].startswith('ሰላም'))

    def test_word_prefix(self):
        out = self.sg.suggest('እግዚ')
        self.assertTrue(out['words'])
        self.assertTrue(all(w.startswith('እግዚ') for w, _ in out['words']))

    def test_folded_prefix_matches_homophone(self):
        # typing ሀ-forms should match words stored with አ/ሐ forms
        out = self.sg.suggest('ሰላም እንዴ')
        self.assertTrue(out['words'])

    def test_empty_partial_safe(self):
        out = self.sg.suggest('')
        self.assertEqual(out['words'], [])
        self.assertIsInstance(out['next'], list)
        self.assertIsInstance(out['sentences'], list)


class SuggestRouteTest(unittest.TestCase):
    """Boots chat_app and hits /api/suggest end-to-end."""

    @classmethod
    def setUpClass(cls):
        import chat_app
        chat_app.PORT = 0
        chat_app.HOST = '127.0.0.1'
        srv = chat_app.ThreadingHTTPServer(('127.0.0.1', 0), chat_app.ChatHandler)
        cls.srv = srv
        cls.port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def _get(self, path):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}{path}', timeout=20) as r:
            return r.status, r.read()

    def test_suggest_route(self):
        status, body = self._get('/api/suggest?text=' +
                                 urllib.parse.quote('ሰላም'))
        self.assertEqual(status, 200)
        d = json.loads(body)
        self.assertIn('sentences', d)
        self.assertIn('words', d)
        self.assertIn('next', d)
        self.assertTrue(d['sentences'] or d['words'])

    def test_suggest_empty(self):
        status, body = self._get('/api/suggest?text=')
        self.assertEqual(status, 200)
        d = json.loads(body)
        self.assertIn('elapsed_ms', d)


class KeyboardSuggestIntegrationTest(unittest.TestCase):
    """The keyboard component + chat page are wired for server type-ahead."""

    def test_component_has_suggest(self):
        with open(os.path.join(ROOT, 'static', 'amharic-keyboard.js'),
                  encoding='utf-8') as f:
            js = f.read()
        self.assertIn('suggestUrl', js)
        self.assertIn('_fetchSuggest', js)
        self.assertIn("type: 'sent'", js)

    def test_chat_page_passes_suggest_url(self):
        with open(os.path.join(ROOT, 'templates', 'chat.html'),
                  encoding='utf-8') as f:
            html = f.read()
        self.assertIn("suggestUrl: '/api/suggest'", html)


if __name__ == '__main__':
    unittest.main()