"""Quality-layer tests: history normalization (the {role,content} crash fix),
smart translator scoring + user corrections, verify/review endpoints, and the
PWA (installable-on-mobile) surfaces."""

import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request


class HistoryNormalizeTest(unittest.TestCase):
    def test_browser_role_content_turns_convert(self):
        from chatbot import normalize_history
        out = normalize_history([
            {'role': 'user', 'content': 'ሰላም'},
            {'role': 'assistant', 'content': 'ሰላም ለአንተ'},
            {'role': 'user', 'content': 'ጥሩ'},
        ])
        self.assertEqual(out[0]['user'], 'ሰላም')
        self.assertEqual(out[0]['source'], 'injected')
        self.assertEqual(out[1]['reply'], 'ሰላም ለአንተ')
        self.assertEqual(out[1]['source'], 'follow_up')

    def test_junk_turns_skipped(self):
        from chatbot import normalize_history
        out = normalize_history([None, 'banana', {'role': 'assistant', 'content': ''},
                                 {'role': 'user', 'content': 'ውሃ'}])
        self.assertEqual([t['user'] for t in out if 'user' in t], ['ውሃ'])

    def test_llm_answer_survives_browser_history(self):
        """Regression: the 'common error' was a KeyError on
        history.append({'role': 'user', 'content': turn['user']})."""
        from chatbot import AmharicAssistant, normalize_history
        a = AmharicAssistant()
        a.history = normalize_history([
            {'role': 'user', 'content': 'ሰላም'},
            {'role': 'assistant', 'content': 'ሰላም ለአንተ'},
        ])
        # will attempt network (no LLM) and return None — the important thing
        # is that building the LLM prompt does NOT raise a KeyError.
        self.assertIsNone(a._llm_answer('ጥሩ'))

    def test_assistant_only_turn_is_safe(self):
        from chatbot import AmharicAssistant
        a = AmharicAssistant()
        a.history = [{'reply': 'የቀድሞ መልስ', 'source': 'history'}]
        self.assertIsNone(a._llm_answer('ጥያቄ'))


class TranslatorScoringTest(unittest.TestCase):
    def setUp(self):
        import translator
        self.translator = translator
        self._real = translator.CORRECTIONS_PATH
        self._dir = tempfile.mkdtemp()
        translator.CORRECTIONS_PATH = os.path.join(self._dir, 'user_translations.json')
        self._clean_state()

    def tearDown(self):
        self.translator.CORRECTIONS_PATH = self._real
        self._clean_state()
        shutil.rmtree(self._dir, ignore_errors=True)

    def _clean_state(self):
        self.translator._CORR[:] = []
        self.translator._CORR_BY_KEY.clear()
        self.translator._CORR_LOADED = False
        self.translator._CACHE.clear()

    def test_offline_glossary_translate(self):
        out = self.translator.best_translate('ሰላም ውሃ ቡና', 'am', 'en', online=False)
        self.assertEqual(out['translated'], 'hello water coffee')
        self.assertEqual(out['engine'], 'lexicon')
        self.assertGreater(out['score'], 0)
        self.assertEqual(len(out['word_evidence']), 3)
        self.assertTrue(all(item['verified'] for item in out['word_evidence']))

    def test_score_prefers_glossary_faithful_candidate(self):
        s_good, _ = self.translator._score('ሰላም', 'hello', 'am', 'en')
        s_bad, _ = self.translator._score('ሰላም', 'zzzz qqqq', 'am', 'en')
        self.assertGreater(s_good, s_bad)
        self.assertTrue(s_bad < 0)

    def test_echo_and_markup_penalised(self):
        s_echo, _ = self.translator._score('ሰው', 'ሰው', 'am', 'en')
        self.assertLess(s_echo, 0)
        s_mark, _ = self.translator._score('ሰው', 'see <b>http://x</b>', 'am', 'en')
        self.assertLess(s_mark, -1)

    def test_correction_store_overrides_engines(self):
        rec = self.translator.store_verification('ሰላም', 'am', 'en',
                                                 'hello', correction='Greetings!')
        self.assertIsNotNone(rec)
        out = self.translator.best_translate('ሰላም', 'am', 'en', online=False)
        self.assertEqual(out['translated'], 'Greetings!')
        self.assertEqual(out['engine'], 'correction')
        self.assertTrue(out['verified'])

    def test_verify_ok_records_and_can_be_reviewed(self):
        self.translator.store_verification('ውሃ', 'am', 'en', 'water')
        items = self.translator.corrections_review()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['text'], 'ውሃ')
        self.assertGreater(self.translator.corrections_count(), 0)

    def test_matching_engine_output_endorses_record(self):
        self.translator.store_verification('ውሃ', 'am', 'en', 'water')
        self.translator.store_verification('ውሃ', 'am', 'en', 'water')
        rec = self.translator.store_verification('ውሃ', 'am', 'en', 'water')
        self.assertGreaterEqual(rec['endorsed'], 2)


class QualityEndpointsTest(unittest.TestCase):
    """Boots chat_app and exercises the new routes end-to-end."""

    @classmethod
    def setUpClass(cls):
        import chat_app
        import translator
        cls.chat_app = chat_app
        cls.translator = translator
        translator.CORRECTIONS_PATH = tempfile.mktemp(prefix='hisar_corr_', suffix='.json')
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
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}{path}', timeout=20) as r:
            return r.status, dict(r.headers), r.read()

    def _post(self, path, body):
        req = urllib.request.Request(
            f'http://127.0.0.1:{self.port}{path}',
            data=json.dumps(body).encode('utf-8'),
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read()

    def test_manifest_and_sw_are_pwa_install_surfaces(self):
        st, h, _ = self._get('/manifest.json')
        self.assertEqual(st, 200)
        self.assertIn('manifest+json', h.get('Content-Type', ''))
        st, h, body = self._get('/sw.js')
        self.assertEqual(st, 200)
        self.assertEqual(h.get('Service-Worker-Allowed'), '/')
        self.assertIn(b'hisar-v1', body)

    def test_pwa_icons_served(self):
        for name in ('icon-180.png', 'icon-192.png', 'icon-512.png'):
            st, h, body = self._get('/static/' + name)
            self.assertEqual(st, 200)
            self.assertIn('image/png', h.get('Content-Type', ''))
            self.assertGreater(len(body), 100)

    def test_chat_page_has_install_and_feedback_hooks(self):
        st, _, body = self._get('/')
        html = body.decode('utf-8')
        self.assertEqual(st, 200)
        self.assertIn('rel="manifest"', html)
        self.assertIn('installBtn', html)
        self.assertIn('serviceWorker', html)
        self.assertIn('/api/translate/verify', html)

    def test_verify_endpoint_and_correction_reuse(self):
        st, body = self._post('/api/translate/verify', {
            'text': 'ሰላም', 'src': 'am', 'dst': 'en',
            'translation': 'hello', 'correct': 'Hello there!'})
        self.assertEqual(st, 200)
        d = json.loads(body)
        self.assertTrue(d['ok'])
        self.assertEqual(d['corrected'], 'Hello there!')

        st, _, body = self._get('/api/translate?text=' + urllib.parse.quote('ሰላም') + '&to=en')
        d = json.loads(body)
        self.assertEqual(d['translated'], 'Hello there!')
        self.assertTrue(d['verified'])
        self.assertEqual(d['engine'], 'correction')

    def test_review_and_health(self):
        st, _, body = self._get('/api/translate/review')
        d = json.loads(body)
        self.assertIn('count', d)
        self.assertIsInstance(d['items'], list)
        st, _, body = self._get('/api/health')
        d = json.loads(body)
        self.assertEqual(d['status'], 'ok')
        self.assertIn('translations', d)

    def test_translate_endpoint_reports_quality_meta(self):
        with urllib.request.urlopen(
                f'http://127.0.0.1:{self.port}/api/translate?text='
                + urllib.parse.quote('ኢትዮጵያ') + '&to=en', timeout=45) as r:
            body = r.read()
        d = json.loads(body)
        self.assertIn('translated', d)
        self.assertIn('score', d)
        self.assertIn('reasons', d)
        # online path: fall back to best reported candidate or stored correction
        if d['engine'] == 'correction':
            self.assertTrue(d['verified'])


if __name__ == '__main__':
    unittest.main()
