"""Tests for the DRF API. Run:  python manage.py test api -v2"""
import json
import os
import tempfile

from django.test import TestCase
from rest_framework.test import APIClient


class ApiTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        import translator
        self.translator = translator
        self._real_path = translator.CORRECTIONS_PATH
        self._tmp = tempfile.mkdtemp()
        translator.CORRECTIONS_PATH = os.path.join(self._tmp, 'user_translations.json')
        translator._CORR[:] = []
        translator._CORR_BY_KEY.clear()
        translator._CORR_LOADED = False
        translator._CORR_REV += 1
        translator._CACHE.clear()
        translator._PAIRS = None
        translator._PAIRS_REV = -1

    def tearDown(self):
        self.translator.CORRECTIONS_PATH = self._real_path
        self.translator._CORR[:] = []
        self.translator._CORR_BY_KEY.clear()
        self.translator._CORR_LOADED = False
        self.translator._CORR_REV += 1
        self.translator._PAIRS = None
        self.translator._PAIRS_REV = -1

    def get_json(self, path, **params):
        resp = self.client.get(path, params)
        return resp, json.loads(resp.content)

    def post_json(self, path, body):
        resp = self.client.post(path, body, format='json')
        try:
            data = json.loads(resp.content)
        except ValueError:
            data = None
        return resp, data


class HealthTest(ApiTestBase):
    def test_health(self):
        resp, data = self.get_json('/api/health/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data['status'], 'ok')
        self.assertIn('llm', data)

    def test_spa_placeholder_when_unbuilt(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('ሕሳር', resp.content.decode('utf-8'))

    def test_manifest_at_root(self):
        resp = self.client.get('/manifest.webmanifest')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('manifest+json', resp['Content-Type'])
        data = resp.json()
        self.assertEqual(data['name'], 'ሕሳር — Amharic AI')
        self.assertEqual(data['start_url'], '/')

    def test_service_worker_scope_header(self):
        resp = self.client.get('/sw.js')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Service-Worker-Allowed'], '/')
        self.assertIn('application/javascript', resp['Content-Type'])

    def test_privacy_page_for_stores(self):
        resp = self.client.get('/privacy')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('የግላዊነት', resp.content.decode('utf-8'))


class ChatApiTest(ApiTestBase):
    def test_math(self):
        resp, data = self.post_json('/api/chat/', {'text': '5 ጠቅላላ 7'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data['source'], 'math')
        self.assertIn('12', data['reply'])

    def test_detailed_answer_has_followups(self):
        resp, data = self.post_json('/api/chat/', {'text': 'AI ምንድን ነው?'})
        self.assertEqual(data['source'], 'intent:ai')
        self.assertIn('ዋና ነጥቦች', data['reply'])
        self.assertTrue(data.get('followups'))
        self.assertTrue(data.get('detail'))

    def test_get_chat(self):
        resp, data = self.get_json('/api/chat/', text='ሰላም')
        self.assertEqual(data['source'], 'intent:greeting')


class TranslateApiTest(ApiTestBase):
    def test_offline_glossary(self):
        resp, data = self.get_json('/api/translate/', text='ሰላም ውሃ', to='en')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('translated', data)
        self.assertIn('score', data)


class ReviewApiTest(ApiTestBase):
    def test_review_only_below_threshold(self):
        resp, data = self.get_json('/api/translations/', status='review', limit=10)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data['threshold'], 0.90)
        for item in data['items']:
            self.assertLess(item['confidence'], 0.90)

    def test_stats(self):
        resp, data = self.get_json('/api/translations/stats/')
        self.assertGreater(data['total'], 0)
        self.assertGreater(data['low_confidence'], 0)

    def test_verify_saves_and_wins(self):
        resp, data = self.post_json('/api/translations/verify/', {
            'text': 'ሰላም', 'src': 'am', 'dst': 'en',
            'translation': 'hello', 'correct': 'Greetings'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data['ok'])
        self.assertEqual(data['corrected'], 'Greetings')
        resp, tr = self.get_json('/api/translate/', text='ሰላም', to='en')
        self.assertEqual(tr['translated'], 'Greetings')
        self.assertEqual(tr['engine'], 'correction')

    def test_verify_requires_translation(self):
        resp, data = self.post_json('/api/translations/verify/', {'text': 'ሰላም'})
        self.assertEqual(resp.status_code, 400)


class SuggestApiTest(ApiTestBase):
    def test_suggest_route(self):
        resp, data = self.get_json('/api/suggest/', text='ሰላም')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('words', data)
        self.assertIn('next', data)
        self.assertIn('sentences', data)

    def test_words_and_ngram(self):
        resp, data = self.get_json('/api/words/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('words', data)
        resp, data = self.get_json('/api/ngram/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('bigram', data)
