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

    def test_spa_or_placeholder_served(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        # Built SPA or the dev placeholder — both identify Zer.
        self.assertIn('ዘር', resp.content.decode('utf-8'))

    def test_manifest_at_root(self):
        resp = self.client.get('/manifest.webmanifest')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('manifest+json', resp['Content-Type'])
        data = resp.json()
        self.assertEqual(data['name'], 'ዘር — Zer · Amharic AI')
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

    def test_chat_stream_sse(self):
        # SSE endpoint must accept text/event-stream (no 406) and always end
        # with a JSON result + [DONE]; rule-brain replies have no deltas.
        resp = self.client.post(
            '/api/chat/stream/', data={'text': 'ሰላም', 'history': []},
            content_type='application/json',
            headers={'Accept': 'text/event-stream'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/event-stream', resp['Content-Type'])
        body = b''.join(resp.streaming_content).decode('utf-8')
        chunks = [c for c in body.split('data: ') if c.strip()]
        self.assertTrue(any('[DONE]' in c for c in chunks))
        self.assertTrue(any('intent:greeting' in c for c in chunks))


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


class ZerLanguageTest(ApiTestBase):
    def test_detect_language(self):
        from zer import detect_language
        self.assertEqual(detect_language('ሰላም እንዴት ነህ?'), 'am')
        self.assertEqual(detect_language('hello, how are you?'), 'en')
        self.assertEqual(detect_language('AI ምንድን ነው?'), 'am')
        self.assertEqual(detect_language('12345'), 'unknown')

    def test_assistant_is_named_zer(self):
        from zer import get_zer
        self.assertEqual(get_zer().name, 'ዘር')

    def test_english_chat_offline_reply(self):
        from zer import get_zer
        r = get_zer().respond('hello there', use_llm=False)
        self.assertEqual(r['lang'], 'en')
        self.assertTrue(r['reply'])
        # Zer must never tell users to connect a language model.
        self.assertNotIn('language model', r['reply'].lower())
        self.assertNotIn('offline right now', r['reply'].lower())

    def test_english_skills_without_llm(self):
        from zer import get_zer
        z = get_zer()
        self.assertIn('96', z.respond('what is 12 times 8', use_llm=False)['reply'])
        self.assertEqual(z.respond('who are you', use_llm=False)['lang'], 'en')
        self.assertTrue(z.respond('tell me about Ethiopia',
                                  use_llm=False)['reply'])

    def test_geez_script_beats_wrong_voice_language(self):
        from zer import get_zer
        # A bad Whisper guess of 'en' must not push Amharic text to English.
        r = get_zer().respond('ሰላም እንዴት ነህ', lang='en', use_llm=False)
        self.assertEqual(r['lang'], 'am')

    def test_amharic_chat_still_works(self):
        resp, data = self.post_json('/api/chat/', {'text': 'ሰላም'})
        self.assertEqual(data['lang'], 'am')
        self.assertEqual(data['source'], 'intent:greeting')


class AuthConversationTest(ApiTestBase):
    def _register(self, username='zerfan'):
        resp = self.client.post('/api/auth/register/', {
            'username': username, 'password': 'secret123', 'display_name': 'Zer Fan',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + data['token'])
        return data

    def test_register_login_and_me(self):
        data = self._register()
        self.assertEqual(data['user']['name'], 'Zer Fan')
        me = self.client.get('/api/auth/me/').json()
        self.assertEqual(me['username'], 'zerfan')
        # logout invalidates the token
        self.client.post('/api/auth/logout/', {}, format='json')
        self.client.credentials()
        resp = self.client.post('/api/auth/register/', {
            'username': 'zerfan', 'password': 'x12345'}, format='json')
        self.assertEqual(resp.status_code, 400)  # taken

    def test_login_rejects_bad_password(self):
        self._register()
        self.client.credentials()
        resp = self.client.post('/api/auth/login/', {
            'username': 'zerfan', 'password': 'wrong'}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_chat_persists_conversation_and_turns(self):
        self._register()
        r = self.client.post('/api/chat/', {'text': 'ሰላም'}, format='json').json()
        self.assertIn('conversation', r)
        convs = self.client.get('/api/conversations/').json()['conversations']
        self.assertEqual(len(convs), 1)
        cid = convs[0]['id']
        detail = self.client.get(f'/api/conversations/{cid}/').json()
        self.assertGreaterEqual(len(detail['turns']), 2)
        r2 = self.client.post('/api/chat/', {
            'text': 'ስለ ኢትዮጵያ ንገረኝ', 'conversation': cid}, format='json').json()
        self.assertEqual(r2['conversation'], cid)
        self.assertEqual(self.client.get('/api/conversations/').json()['conversations'].__len__(), 1)

    def test_anonymous_chat_is_not_persisted(self):
        self.client.credentials()
        r = self.client.post('/api/chat/', {'text': 'ሰላም'}, format='json').json()
        self.assertNotIn('conversation', r)

    def test_conversation_is_private_to_owner(self):
        self._register('alice')
        cid = self.client.post('/api/conversations/', {'title': 'mine'}, format='json').json()['id']
        self.client.credentials()
        self._register('bob')
        self.assertEqual(self.client.get(f'/api/conversations/{cid}/').status_code, 404)

    def test_taught_fact_is_remembered_on_account(self):
        self._register()
        self.client.post('/api/chat/',
                         {'text': 'አስታውስ የማርያም ቡና ጥቁር ነው'}, format='json')
        mems = self.client.get('/api/memories/').json()['memories']
        self.assertTrue(any('ማርያም' in m['fact'] for m in mems))


class ZerBrainTest(ApiTestBase):
    def test_offline_amharic_code_generation(self):
        import codegen
        out = codegen.generate('ፓይቶን ኮድ ጻፍልኝ ድምር')
        self.assertIsNotNone(out)
        self.assertIn('```python', out)
        self.assertIn('ድምር', out)          # Amharic identifier
        self.assertIn('ለማስኬድ', out)          # Amharic explanation

    def test_chat_returns_amharic_code(self):
        resp, data = self.post_json('/api/chat/', {'text': 'ፓይቶን ኮድ ጻፍልኝ ድምር'})
        self.assertEqual(data['source'], 'code')
        self.assertIn('```python', data['reply'])

    def test_spoken_language_reconciliation(self):
        from zer_speech import detect_spoken_language
        self.assertEqual(detect_spoken_language('ሰላም እንዴት ነህ', 'en'), 'am')
        self.assertEqual(detect_spoken_language('hello how are you', 'am'), 'en')

    def test_keyword_intent_fallback(self):
        from zer import get_zer
        tag, score = get_zer()._am._keyword_intent('ስለ ኢትዮጵያ ጥንታዊ ታሪክ')
        self.assertEqual(tag, 'ethiopia')
        self.assertGreater(score, 0)
        # Ambiguous queries must not guess an intent.
        ambiguous, _ = get_zer()._am._keyword_intent('ስለ ጤና')
        self.assertIsNone(ambiguous)


class LearningTest(ApiTestBase):
    """Corrections taught in /review change how Zer responds."""

    def test_teach_then_zer_uses_it(self):
        from zer import get_zer
        # Before teaching, an unknown word isn't answered from the glossary.
        before = get_zer().respond('ጥምቀት ምን ማለት ነው?', use_llm=False)
        self.assertNotEqual(before['source'], 'learned')

        # Teach via the review API.
        resp, data = self.post_json('/api/translations/verify/', {
            'text': 'ጥምቀት', 'src': 'am', 'dst': 'en',
            'translation': '', 'correct': 'baptism'})
        self.assertTrue(data['ok'])

        after = get_zer().respond('ጥምቀት ምን ማለት ነው?', use_llm=False)
        self.assertEqual(after['source'], 'learned')
        self.assertIn('baptism', after['reply'])

    def test_english_question_uses_learned_pair(self):
        from zer import get_zer
        self.post_json('/api/translations/verify/', {
            'text': 'ቡና', 'src': 'am', 'dst': 'en',
            'translation': '', 'correct': 'coffee drink'})
        r = get_zer().respond('translate ቡና in english', use_llm=False)
        self.assertEqual(r['source'], 'learned')
        self.assertIn('coffee drink', r['reply'])

    def test_learning_stats_endpoint(self):
        resp, data = self.get_json('/api/learning/stats/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('learned', data)
        start = data['learned']
        self.post_json('/api/translations/verify/', {
            'text': 'ውሃ', 'src': 'am', 'dst': 'en',
            'translation': '', 'correct': 'water'})
        resp, data = self.get_json('/api/learning/stats/')
        self.assertEqual(data['learned'], start + 1)


class SpeechApiTest(ApiTestBase):
    def test_status_shape(self):
        resp, data = self.get_json('/api/speech/status/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('stt', data)
        self.assertIn('tts', data)
        self.assertIn('available', data['stt'])
        self.assertIn('available', data['tts'])

    def test_transcribe_requires_audio(self):
        resp = self.client.post('/api/speech/transcribe/', {}, format='multipart')
        self.assertEqual(resp.status_code, 400)

    def test_synthesize_requires_text(self):
        resp, data = self.post_json('/api/speech/synthesize/', {})
        self.assertEqual(resp.status_code, 400)

    def test_voice_turn_requires_audio(self):
        resp = self.client.post('/api/voice/turn/', {}, format='multipart')
        self.assertEqual(resp.status_code, 400)

    def test_voices_endpoint_exposes_controls(self):
        resp, data = self.get_json('/api/speech/voices/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('voices', data)
        self.assertIn('defaults', data)
        self.assertIn('ranges', data)
        self.assertIn('voice', data['defaults']['am'])
        self.assertIn('rate', data['ranges'])

    def test_synthesize_accepts_voice_tuning(self):
        resp, _ = self.post_json('/api/speech/synthesize/', {
            'text': 'ሰላም', 'lang': 'am', 'rate': 120, 'pitch': 30, 'volume': 80})
        # No TTS engine in CI → 503, but the params must validate (not 400).
        self.assertIn(resp.status_code, (200, 503))


class DictionaryApiTest(ApiTestBase):
    def test_letter_index(self):
        resp, data = self.get_json('/api/dictionary/letters/')
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(data['count'], 1000)
        self.assertGreater(len(data['letters']), 20)
        sample = data['letters'][0]
        self.assertIn('letter', sample)
        self.assertIn('count', sample)

    def test_words_grouped_by_letter(self):
        from amharic_nlp.letters import letter_of
        resp, data = self.get_json('/api/dictionary/', letter='ሀ', limit=20)
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(data['total'], 0)
        self.assertTrue(data['words'])
        for entry in data['words']:
            self.assertEqual(letter_of(entry['w']), 'ሀ')

    def test_letter_param_required(self):
        resp, data = self.get_json('/api/dictionary/')
        self.assertEqual(resp.status_code, 400)

    def test_review_items_carry_translation_and_letter(self):
        resp, data = self.get_json('/api/translations/', status='all', limit=10)
        for item in data['items']:
            self.assertIn('en', item)
            self.assertIn('letter', item)

    def test_translation_letters_and_filter(self):
        resp, data = self.get_json('/api/translations/letters/')
        self.assertEqual(resp.status_code, 200)
        letters = [row['letter'] for row in data['letters']]
        self.assertTrue(letters)
        target = letters[0]
        resp, page = self.get_json('/api/translations/', status='all', letter=target, limit=50)
        self.assertTrue(all(i['letter'] == target for i in page['items']))


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
