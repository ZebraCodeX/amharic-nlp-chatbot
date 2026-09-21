#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Bible-trained language model, the LLM client and the
hybrid (rule + LLM) reply routing. Run:  python3 -m unittest -v"""
import json
import os
import tempfile
import unittest
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
import sys
sys.path.insert(0, ROOT)

from amharic_nlp import AmharicNormalizer
import llm


class MockBackend(BaseHTTPRequestHandler):
    seen = []
    reply = {'choices': [{'message': {'content': 'የፈተና መልስ'}}]}

    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(n))
        type(self).seen.append(body)
        out = json.dumps(type(self).reply).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


class NGramModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from amharic_nlp import NLModel
        cls.nl = NLModel()
        assert cls.nl.load(), 'nl_model.json missing — run: python3 -m amharic_nlp.training'

    def test_model_loaded(self):
        self.assertIn('bigram', self.nl.data)
        self.assertGreater(len(self.nl.data['unigram']), 1000)

    def test_predict(self):
        picks = self.nl.next_words(('እግዚአብሔር',))
        self.assertIsInstance(picks, list)
        for w, c in picks[:1]:
            self.assertTrue(w.strip())

    def test_common_words(self):
        words = self.nl.common_words(500)
        self.assertLessEqual(len(words), 500)


class LLMClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(('127.0.0.1', 0), MockBackend)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_chat_returns_text(self):
        old = os.environ.get('LLM_BASE_URL')
        old_pref = os.environ.get('ZER_LLM_BACKEND')
        os.environ['LLM_BASE_URL'] = f'http://127.0.0.1:{self.port}/v1'
        os.environ['ZER_LLM_BACKEND'] = 'remote'
        try:
            llm.clear_cache()
            out = llm.chat('system', 'user')
            self.assertEqual(out, 'የፈተና መልስ')
            msg = MockBackend.seen[-1]['messages']
            self.assertEqual(msg[0]['role'], 'system')
        finally:
            if old is None:
                os.environ.pop('LLM_BASE_URL', None)
            else:
                os.environ['LLM_BASE_URL'] = old
            if old_pref is None:
                os.environ.pop('ZER_LLM_BACKEND', None)
            else:
                os.environ['ZER_LLM_BACKEND'] = old_pref

    def test_embedded_model_preferred_over_remote(self):
        """The bundled trained model wins even when LLM_BASE_URL is configured."""
        old = os.environ.get('LLM_BASE_URL')
        old_pref = os.environ.get('ZER_LLM_BACKEND')
        os.environ['LLM_BASE_URL'] = f'http://127.0.0.1:{self.port}/v1'
        os.environ.pop('ZER_LLM_BACKEND', None)
        import types
        fake = types.ModuleType('zer_model')
        fake.available = lambda: True
        fake.status = lambda: {'model': 'zer-qwen-q4_k_m.gguf'}
        fake.chat = (lambda system, user, history=None, model=None,
                     max_tokens=0: 'ዘር ከembedded')
        fake.chat_stream = lambda *a, **k: iter(['ዘር'])
        old_mod = sys.modules.get('zer_model')
        sys.modules['zer_model'] = fake
        try:
            llm.clear_cache()
            llm._embedded_cached = None
            self.assertEqual(llm.chat('s', 'u'), 'ዘር ከembedded')
            self.assertEqual(llm.which()[0], 'embedded')
        finally:
            llm._embedded_cached = None
            if old_mod is None:
                sys.modules.pop('zer_model', None)
            else:
                sys.modules['zer_model'] = old_mod
            if old is None:
                os.environ.pop('LLM_BASE_URL', None)
            else:
                os.environ['LLM_BASE_URL'] = old
            if old_pref is None:
                os.environ.pop('ZER_LLM_BACKEND', None)
            else:
                os.environ['ZER_LLM_BACKEND'] = old_pref


class HybridRoutingTest(unittest.TestCase):
    def _monkey(self):
        """Stub the LLM with a deterministic reply, then restore."""
        import chatbot
        real = getattr(chatbot.AmharicAssistant, '_llm_answer')
        chatbot.AmharicAssistant._llm_answer = (
            lambda self, text, on_delta=None: '[LLM] ' + text)
        self.addCleanup(setattr,
                        chatbot.AmharicAssistant, '_llm_answer', real)
        from chatbot import AmharicAssistant
        return AmharicAssistant()

    def test_math_stays_rule_even_with_llm(self):
        a = self._monkey()
        r = a.respond('5 ጠቅላላ 7', use_llm=True)
        self.assertEqual(r['source'], 'math')
        self.assertIn('12', r['reply'])

    def test_creative_request_uses_llm(self):
        a = self._monkey()
        r = a.respond('ስለ ቡና ግጥም ጻፍልኝ', use_llm=True)
        self.assertEqual(r['source'], 'llm')

    def test_open_ended_uses_llm(self):
        a = self._monkey()
        r = a.respond('ስለ ኮስሞስ ንገረኝ የምስጢር ነገር', use_llm=True)
        self.assertEqual(r['source'], 'llm')

    def test_language_gate_stays(self):
        a = self._monkey()
        r = a.respond('hello world')
        self.assertEqual(r['source'], 'language_gate')

    def test_offline_fallback(self):
        from chatbot import AmharicAssistant
        a = AmharicAssistant()
        real = a._llm_answer
        a._llm_answer = lambda text: None
        self.addCleanup(setattr, a, '_llm_answer', real)
        r = a.respond('ስለ የማይታወቅ ጉዳይ xyz', use_llm=True)
        self.assertEqual(r['source'], 'fallback')


class EtCalendarTest(unittest.TestCase):
    """Gregorian ⇄ Ethiopic conversions & Amharic names (et_calendar.py)."""

    def test_known_boundaries(self):
        import et_calendar as et
        self.assertEqual(et.gregorian_to_ethiopic(2007, 9, 11), (2000, 1, 1))   # NY 2000 ዓ.ም
        self.assertEqual(et.gregorian_to_ethiopic(2026, 9, 11), (2019, 1, 1))   # NY 2019 ዓ.ም
        self.assertEqual(et.gregorian_to_ethiopic(2026, 9, 10), (2018, 13, 5))  # ጳጉሜ 5
        self.assertEqual(et.gregorian_to_ethiopic(1970, 1, 1), (1962, 4, 23))   # ታኅሣሥ 23
        self.assertEqual(et.gregorian_to_ethiopic(2028, 9, 10), (2020, 13, 6))  # leap ጳጉሜ 6

    def test_round_trip(self):
        import et_calendar as et
        for g in [(2026, 9, 10), (2027, 2, 28), (2028, 2, 29), (2000, 1, 1),
                  (1999, 8, 7), (1900, 3, 15)]:
            e = et.gregorian_to_ethiopic(*g)
            self.assertEqual(et.ethiopic_to_gregorian(*e), g)

    def test_weekday_names(self):
        import et_calendar as et
        self.assertEqual(et.weekday(2026, 9, 10), 'ሐሙስ')          # a known Thursday
        self.assertEqual(et.weekday(2007, 9, 11), 'ማክሰኞ')         # NY 2000 ዓ.ም
        self.assertIn(et.weekday(2026, 9, 10), et.WEEKDAYS)


class ClockDateRandomTest(unittest.TestCase):
    """ሕሳር tells the real time, the Amharic (Ethiopic) date and picks lots."""

    @classmethod
    def setUpClass(cls):
        from chatbot import AmharicAssistant
        cls.a = AmharicAssistant()

    def test_time_clock(self):
        r = self.a.respond('ስንት ሰዓት ነው?')
        self.assertEqual(r['source'], 'time')
        self.assertIn('ሰዓት', r['reply'])

    def test_time_ahoon(self):
        r = self.a.respond('አሁን ስንት ሰዓት')
        self.assertEqual(r['source'], 'time')

    def test_date_ethiopian(self):
        r = self.a.respond('ዛሬ ምን ቀን ነው?')
        self.assertEqual(r['source'], 'date')
        self.assertIn('ዓ.ም', r['reply'])
        # month + era must both be present (e.g. "ጳጉሜ 5, 2018 ዓ.ም")
        import et_calendar as et
        self.assertTrue(any(m in r['reply'] for m in et.MONTHS))

    def test_date_samt(self):
        r = self.a.respond('ሳምንቱ ስንት ነው?')
        self.assertEqual(r['source'], 'date')

    def test_coin(self):
        r = self.a.respond('ሳንቲም ጣልልኝ')
        self.assertEqual(r['source'], 'random')
        self.assertTrue('ጭንቅላት' in r['reply'] or 'ጅራት' in r['reply'])

    def test_dice(self):
        r = self.a.respond('ዳይስ ጣል')
        self.assertEqual(r['source'], 'random')

    def test_etheta(self):
        r = self.a.respond('ዕጣ ቅዳልኝ')
        self.assertEqual(r['source'], 'random')
        self.assertIn('ወጣ', r['reply'])

    def test_greeting_has_time_of_day(self):
        r = self.a.respond('ሰላም')
        self.assertEqual(r['source'], 'intent:greeting')
        self.assertTrue(any(s in r['reply'] for s in
                            ('መልካም ጥዋት', 'ውብ ቀን', 'መልካም ምሽት', 'መልካም ሌሊት')))


class CreativeOfflineTest(unittest.TestCase):
    def test_poem(self):
        import creative
        out = creative.creative_answer('ስለ ቡና ግጥም ጻፍልኝ')
        self.assertTrue(out and out.startswith('ግጥም') and 'ቡና' in out)

    def test_website(self):
        import creative
        out = creative.creative_answer('ስለ ቡና ድረ ገጽ አዘጋጅልኝ')
        self.assertIn('<!doctype html>', out)

    def test_plan(self):
        import creative
        out = creative.creative_answer('ለትምህርቴ እቅድ አዘጋጅልኝ')
        self.assertTrue(out.startswith('እቅድ'))

    def test_not_creative(self):
        import creative
        self.assertIsNone(creative.creative_answer('ስለ ኮስሞስ ንገረኝ'))
        self.assertIsNone(creative.creative_answer('5 ጠቅላላ 7'))


class ServerTest(unittest.TestCase):
    """Boots a real chat_app instance on an ephemeral port and hits key routes."""

    @classmethod
    def setUpClass(cls):
        import chat_app
        chat_app.PORT = 0
        chat_app.HOST = '127.0.0.1'
        srv = chat_app.ThreadingHTTPServer(('127.0.0.1', 0), chat_app.ChatHandler)
        cls.srv = srv
        cls.port = srv.server_address[1]
        import threading
        threading.Thread(target=srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def _get(self, path):
        import urllib.request
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}{path}', timeout=15) as r:
            return r.status, r.read()

    def test_health(self):
        status, body = self._get('/api/health')
        self.assertEqual(status, 200)
        self.assertIn(b'ok', body)

    def test_chat_math(self):
        import urllib.request, json
        req = urllib.request.Request(
            f'http://127.0.0.1:{self.port}/api/chat',
            data=json.dumps({'text': '5 ጠቅላላ 7'}).encode(),
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        self.assertEqual(data['source'], 'math')
        self.assertIn('12', data['reply'])

    def test_chat_date(self):
        import urllib.request, json
        req = urllib.request.Request(
            f'http://127.0.0.1:{self.port}/api/chat',
            data=json.dumps({'text': 'ዛሬ ምን ቀን ነው?'}).encode(),
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        self.assertEqual(data['source'], 'date')
        self.assertIn('ዓ.ም', data['reply'])

    def test_static_served(self):
        status, body = self._get('/static/amharic-keyboard.js')
        self.assertEqual(status, 200)
        self.assertIn(b'AmharicKeyboard', body)

    def test_keyboard_page(self):
        status, body = self._get('/keyboard')
        self.assertEqual(status, 200)
        self.assertIn(b'AmharicKeyboard', body)

    def test_chat_page(self):
        status, body = self._get('/')
        self.assertEqual(status, 200)
        self.assertIn(b'AmharicKeyboard', body)
        self.assertIn(b'/static/amharic-keyboard', body)


if __name__ == '__main__':
    unittest.main()