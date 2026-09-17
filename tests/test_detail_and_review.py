#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the 2026 upgrade: in-depth knowledge answers (rich_answers.json),
the Werket-style phonetic keyboard surface, and the translation review API/UI.
Run:  python3 -m unittest -v tests.test_detail_and_review
"""

import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)


class DetailedAnswerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from chatbot import AmharicAssistant
        cls.a = AmharicAssistant()

    def test_substantive_intent_is_detailed(self):
        r = self.a.respond('AI ምንድን ነው?', use_llm=False)
        self.assertEqual(r['source'], 'intent:ai')
        self.assertIn('ዋና ነጥቦች', r['reply'])
        self.assertGreaterEqual(r['reply'].count('•'), 3)
        self.assertTrue(r.get('followups'))
        self.assertTrue(r.get('detail'))

    def test_greeting_stays_short(self):
        r = self.a.respond('ሰላም', use_llm=False)
        self.assertEqual(r['source'], 'intent:greeting')
        self.assertNotIn('ዋና ነጥቦች', r['reply'])

    def test_short_request_is_concise(self):
        r = self.a.respond('ስለ ኢትዮጵያ በአጭሩ ንገረኝ', use_llm=False)
        self.assertNotIn('ዋና ነጥቦች', r['reply'])

    def test_follow_up_deepens_with_more_points(self):
        self.a.respond('ስለ ኢትዮጵያ ንገረኝ', use_llm=False)
        r = self.a.respond('እና ታዲያ?', use_llm=False)
        self.assertEqual(r['source'], 'follow_up')
        self.assertIn('ተጨማሪ ነጥቦች', r['reply'])

    def test_rich_answers_file_is_valid(self):
        path = os.path.join(ROOT, 'data', 'rich_answers.json')
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        answers = data['answers']
        self.assertGreaterEqual(len(answers), 30)
        for tag, entry in answers.items():
            self.assertTrue(entry.get('summary'), tag)
            self.assertTrue(entry.get('points'), tag)
            self.assertIsInstance(entry.get('followups'), list)

    def test_rich_answers_cover_knowledge_base_tags(self):
        kb_tags = {i['tag'] for i in self.a.intents}
        from chatbot import SHORT_TAGS
        missing = kb_tags - SHORT_TAGS - set(self.a.rich)
        self.assertEqual(missing, set(), f'no detailed content for: {sorted(missing)}')


class PhoneticKeyboardAssetTest(unittest.TestCase):
    """The keyboard component ships the Werket phonetic engine."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, 'static', 'amharic-keyboard.js'), encoding='utf-8') as f:
            cls.js = f.read()
        with open(os.path.join(ROOT, 'static', 'amharic-keyboard.css'), encoding='utf-8') as f:
            cls.css = f.read()
        with open(os.path.join(ROOT, 'templates', 'chat.html'), encoding='utf-8') as f:
            cls.chat = f.read()

    def test_component_exposes_compose_and_phonetic(self):
        for token in ('compose', 'PHONETIC', 'DIGRAPHS', 'ordersFor',
                      'togglePhonetic', '_phoneticType', 'QWERTY'):
            self.assertIn(token, self.js)

    def test_css_has_phonetic_toggle_styles(self):
        self.assertIn('.akb-mode-toggle', self.css)
        self.assertIn('.akb-key.latin', self.css)

    def test_chat_page_defaults_to_amharic_keyboard(self):
        # The on-screen keyboard must be the Amharic Fidel layout by default;
        # phonetic (Latin→Ge'ez) typing is an opt-in toggle, not the default.
        self.assertIn('phonetic: false', self.chat)
        self.assertNotIn('phonetic: true', self.chat)
        self.assertIn('amharic-keyboard.js', self.chat)
        self.assertIn('/review', self.chat)

    def test_component_phonetic_is_opt_in(self):
        self.assertIn('this.phonetic = !!options.phonetic', self.js)
        # The Fidel (Amharic) letters page exists and is the non-phonetic default.
        self.assertIn('akb-key char', self.js)
        self.assertIn('akb-key latin', self.js)

    def test_compose_known_words(self):
        # Mirrors the Werket README examples: selam → ሰላም, buna → ቡና.
        self.assertIn("sh:'ሸ'", self.js)
        self.assertIn("'ሸ'", self.js)


class TranslationReviewTest(unittest.TestCase):
    def setUp(self):
        import translator
        self.translator = translator
        self._real = translator.CORRECTIONS_PATH
        self._dir = tempfile.mkdtemp()
        translator.CORRECTIONS_PATH = os.path.join(self._dir, 'user_translations.json')
        self._clean()
        translator._PAIRS = None
        translator._PAIRS_REV = -1

    def tearDown(self):
        self.translator.CORRECTIONS_PATH = self._real
        self._clean()
        self.translator._PAIRS = None
        self.translator._PAIRS_REV = -1
        shutil.rmtree(self._dir, ignore_errors=True)

    def _clean(self):
        t = self.translator
        t._CORR[:] = []
        t._CORR_BY_KEY.clear()
        t._CORR_LOADED = False
        t._CORR_REV += 1
        t._CACHE.clear()

    def test_review_shows_only_below_threshold(self):
        d = self.translator.list_translations(status='review', limit=10)
        self.assertGreater(d['total'], 10)
        self.assertEqual(d['threshold'], self.translator.CONFIDENCE_THRESHOLD)
        for item in d['items']:
            self.assertLess(item['confidence'], 0.90)
            for key in ('am', 'en', 'status', 'source', 'confidence'):
                self.assertIn(key, item)
        # sorted most-uncertain first
        confs = [i['confidence'] for i in d['items']]
        self.assertEqual(confs, sorted(confs))

    def test_high_confidence_rows_are_hidden_from_review(self):
        # a curated, unambiguous glossary word scores >= 90% and is not queued
        rows = self.translator.list_translations(status='all')['items']
        high = [p for p in rows if p['confidence'] >= 0.90]
        self.assertTrue(high, 'expected some >=90% rows')
        review_ams = {i['am'] for i in
                      self.translator.list_translations(status='review', limit=500)['items']}
        self.assertTrue(all(p['am'] not in review_ams for p in high))

    def test_stats_counts(self):
        stats = self.translator.translation_stats()
        self.assertGreater(stats['glossary'], 50)
        self.assertGreater(stats['review'], 0)
        self.assertGreater(stats['low_confidence'], 0)
        self.assertEqual(stats['verified'], 0)
        self.assertEqual(stats['low_confidence'] + stats['high_confidence'],
                         stats['total'])

    def test_correction_raises_confidence_above_threshold(self):
        self.translator.store_verification('ሰላም', 'am', 'en', 'hello',
                                           correction='Greetings')
        row = self.translator.list_translations(query='ሰላም', status='all')['items'][0]
        self.assertGreaterEqual(row['confidence'], 0.90)

    def test_correction_moves_row_to_corrected(self):
        self.translator.store_verification('ሰላም', 'am', 'en', 'hello',
                                           correction='Greetings')
        d = self.translator.list_translations(status='corrected')
        ams = [i['am'] for i in d['items']]
        self.assertIn('ሰላም', ams)
        self.assertEqual(self.translator.translation_stats()['corrected'], 1)

    def test_approval_marks_verified(self):
        self.translator.store_verification('ሰላም', 'am', 'en', 'hello')
        d = self.translator.list_translations(status='verified')
        self.assertIn('ሰላም', [i['am'] for i in d['items']])

    def test_search_filters(self):
        d = self.translator.list_translations(query='ሰላም', status='all')
        self.assertTrue(all('ሰላም' in i['am'] or 'ሰላም' in i['en'] for i in d['items']))

    def test_cache_invalidates_after_correction(self):
        before = self.translator.translation_stats()['verified']
        self.translator.store_verification('ውሃ', 'am', 'en', 'water')
        after = self.translator.translation_stats()['verified']
        self.assertEqual(after, before + 1)


class ReviewEndpointsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import chat_app
        import translator
        cls.chat_app = chat_app
        cls.translator = translator
        translator.CORRECTIONS_PATH = tempfile.mktemp(prefix='hisar_rev_', suffix='.json')
        translator._PAIRS = None
        translator._PAIRS_REV = -1
        cls.srv = chat_app.ThreadingHTTPServer(('127.0.0.1', 0), chat_app.ChatHandler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        try:
            os.remove(cls.translator.CORRECTIONS_PATH)
        except Exception:
            pass

    def _get(self, path):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}{path}', timeout=30) as r:
            return r.status, r.read()

    def _post(self, path, body):
        req = urllib.request.Request(
            f'http://127.0.0.1:{self.port}{path}',
            data=json.dumps(body).encode('utf-8'),
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())

    def test_review_page_served(self):
        st, body = self._get('/review')
        self.assertEqual(st, 200)
        html = body.decode('utf-8')
        self.assertIn('translations.js', html)
        self.assertIn('amharic-keyboard.js', html)

    def test_translations_endpoint(self):
        st, body = self._get('/api/translations?status=review&limit=5')
        d = json.loads(body)
        self.assertEqual(st, 200)
        self.assertIn('total', d)
        self.assertLessEqual(len(d['items']), 5)

    def test_stats_endpoint(self):
        st, body = self._get('/api/translations/stats')
        d = json.loads(body)
        self.assertEqual(st, 200)
        self.assertIn('review', d)
        self.assertIn('untranslated', d)

    def test_verify_accepts_new_translation_for_untranslated_word(self):
        st, body = self._get('/api/translations?status=untranslated&limit=1')
        item = json.loads(body)['items'][0]
        st, d = self._post('/api/translations/verify', {
            'text': item['am'], 'src': 'am', 'dst': 'en',
            'translation': '', 'correct': 'corrected-word'})
        self.assertEqual(st, 200)
        self.assertTrue(d['ok'])
        self.assertEqual(d['corrected'], 'corrected-word')
        # the correction now wins in the translator
        st, body = self._get('/api/translate?text='
                             + urllib.parse.quote(item['am']) + '&to=en')
        out = json.loads(body)
        self.assertEqual(out['translated'], 'corrected-word')
        self.assertEqual(out['engine'], 'correction')


if __name__ == '__main__':
    unittest.main()
