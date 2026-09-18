"""REST API views (DRF) wrapping the pure-stdlib NLP + speech services."""
import base64
import json

from django.conf import settings
from django.http import HttpResponse
from django.views import View
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated

from . import services
from .models import Conversation, Memory, Turn
from .serializers import (
    ChatRequestSerializer,
    ConversationDetailSerializer,
    ConversationSerializer,
    LoginSerializer,
    MemorySerializer,
    RegisterSerializer,
    TranslateQuerySerializer,
    UserSerializer,
    VerifySerializer,
)

User = get_user_model()


def _auth_payload(user):
    token, _ = Token.objects.get_or_create(user=user)
    return {'token': token.key, 'user': UserSerializer(user).data}


def _persist_turns(request, text, reply, lang, source, conversation_id=None):
    """Save a user/assistant turn pair for authenticated users. Returns id."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return None
    conv = None
    if conversation_id:
        conv = Conversation.objects.filter(id=conversation_id, user=user).first()
    if conv is None:
        conv = Conversation.objects.create(user=user, title=(text or '')[:60],
                                           lang=lang or '')
    Turn.objects.create(conversation=conv, role='user', text=text or '', lang=lang or '')
    Turn.objects.create(conversation=conv, role='assistant', text=reply or '',
                        lang=lang or '', source=source or '')
    if not conv.title:
        conv.title = (text or '')[:60]
    conv.lang = lang or conv.lang
    conv.updated = timezone.now()
    conv.save(update_fields=['title', 'lang', 'updated'])
    return conv.id


def _int_param(request, name, default, lo, hi):
    try:
        return max(lo, min(int(request.query_params.get(name, default)), hi))
    except (TypeError, ValueError):
        return default


class RegisterView(APIView):
    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.save()
        return Response(_auth_payload(user), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(_auth_payload(ser.validated_data['user']))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({'ok': True})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            **UserSerializer(request.user).data,
            'conversations': request.user.conversations.count(),
            'memories': request.user.memories.count(),
        })


class ConversationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = request.user.conversations.all()[:200]
        return Response({'conversations': ConversationSerializer(qs, many=True).data})

    def post(self, request):
        conv = Conversation.objects.create(
            user=request.user,
            title=(request.data.get('title') or '')[:140],
            lang=(request.data.get('lang') or '')[:8],
        )
        return Response(ConversationDetailSerializer(conv).data,
                        status=status.HTTP_201_CREATED)


class ConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request, pk):
        return Conversation.objects.filter(pk=pk, user=request.user).first()

    def get(self, request, pk):
        conv = self._get(request, pk)
        if not conv:
            return Response({'error': 'not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ConversationDetailSerializer(conv).data)

    def patch(self, request, pk):
        conv = self._get(request, pk)
        if not conv:
            return Response({'error': 'not found'}, status=status.HTTP_404_NOT_FOUND)
        if 'title' in request.data:
            conv.title = (request.data.get('title') or '')[:140]
            conv.save(update_fields=['title', 'updated'])
        return Response(ConversationSerializer(conv).data)

    def delete(self, request, pk):
        conv = self._get(request, pk)
        if conv:
            conv.delete()
        return Response({'ok': True})


class MemoryListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = request.user.memories.all()[:200]
        return Response({'memories': MemorySerializer(qs, many=True).data})

    def post(self, request):
        fact = (request.data.get('fact') or '').strip()
        if not fact:
            return Response({'error': 'fact required'}, status=status.HTTP_400_BAD_REQUEST)
        mem = Memory.objects.create(user=request.user, fact=fact[:500])
        return Response(MemorySerializer(mem).data, status=status.HTTP_201_CREATED)

    def delete(self, request):
        pk = request.data.get('id') or request.query_params.get('id')
        request.user.memories.filter(pk=pk).delete()
        return Response({'ok': True})


class ChatView(APIView):
    """POST {text, history?, lang?, conversation?} → Zer's reply (persisted for
    signed-in users)."""
    throttle_scope = 'chat'

    def post(self, request):
        ser = ChatRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        result = services.chat(data['text'], data.get('history'),
                               data.get('lang') or None,
                               user=request.user if request.user.is_authenticated else None)
        conv_id = _persist_turns(request, data['text'], result.get('reply'),
                                 result.get('lang'), result.get('source'),
                                 request.data.get('conversation'))
        if conv_id:
            result['conversation'] = conv_id
        return Response(result)

    def get(self, request):
        history = None
        raw = request.query_params.get('history')
        if raw:
            try:
                history = json.loads(raw)
            except ValueError:
                history = None
        lang = request.query_params.get('lang') or None
        return Response(services.chat(
            request.query_params.get('text', ''), history, lang,
            user=request.user if request.user.is_authenticated else None))


class TranslateView(APIView):
    throttle_scope = 'translate'
    def get(self, request):
        ser = TranslateQuerySerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        text = ser.validated_data['text']
        to = ser.validated_data['to']
        src = 'am' if to == 'en' else 'en'
        return Response(services.translate(text, src, to))


class TranslationsView(APIView):
    def get(self, request):
        return Response(services.translations(
            query=request.query_params.get('q', ''),
            status=request.query_params.get('status', 'review'),
            limit=_int_param(request, 'limit', 50, 1, 500),
            offset=_int_param(request, 'offset', 0, 0, 10_000_000),
            max_confidence=request.query_params.get('max_confidence') or None,
            letter=request.query_params.get('letter') or None,
        ))


class TranslationStatsView(APIView):
    def get(self, request):
        return Response(services.translation_stats())


class TranslationLettersView(APIView):
    def get(self, request):
        return Response(services.translation_letters())


class LearningStatsView(APIView):
    """How many translations Zer has learned from the review UI."""

    def get(self, request):
        return Response(services.learning_stats())


class DictionaryLettersView(APIView):
    def get(self, request):
        return Response(services.dictionary_letters())


class DictionaryView(APIView):
    def get(self, request):
        letter = request.query_params.get('letter') or ''
        if not letter:
            return Response({'error': 'letter required'},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(services.dictionary_by_letter(
            letter,
            limit=_int_param(request, 'limit', 100, 1, 1000),
            offset=_int_param(request, 'offset', 0, 0, 10_000_000),
        ))


class TranslationVerifyView(APIView):
    def post(self, request):
        ser = VerifySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            rec = services.verify_translation(
                d['text'], d.get('src') or 'am', d.get('dst') or 'en',
                d.get('translation', ''), correction=d.get('correct', ''),
                engine=d.get('engine') or 'user')
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'ok': True, 'id': rec['id'], 'corrected': rec['corrected'],
                         'endorsed': rec.get('endorsed', 0)})


class CorrectionsReviewView(APIView):
    def get(self, request):
        limit = _int_param(request, 'limit', 100, 1, 500)
        items = services.corrections_review(limit)
        return Response({'count': len(items), 'items': items})


class WordsView(APIView):
    def get(self, request):
        # Flat list only — the keyboard doesn't need the per-letter index.
        data = services.words()
        return Response({'count': data.get('count'), 'words': data.get('words', [])})


class NgramView(APIView):
    def get(self, request):
        return Response(services.ngram())


class SuggestView(APIView):
    def get(self, request):
        return Response(services.suggest(request.query_params.get('text', '')))


class LlmStatusView(APIView):
    def get(self, request):
        return Response(services.llm_status())


def _voice_params(data):
    """Extract the optional TTS tuning parameters from a request body."""
    out = {}
    if data.get('voice'):
        out['voice'] = str(data.get('voice'))
    for key in ('rate', 'pitch', 'volume', 'gap'):
        raw = data.get(key)
        if raw not in (None, ''):
            try:
                out[key] = int(float(raw))
            except (TypeError, ValueError):
                pass
    return out


class SpeechStatusView(APIView):
    """Which open-source STT/TTS providers are available in this deployment."""

    def get(self, request):
        try:
            return Response(services.speech_status())
        except Exception as exc:
            return Response({'stt': {'available': False}, 'tts': {'available': False},
                             'error': str(exc)})


class SpeechVoicesView(APIView):
    """Available voices + tunable ranges (rate/pitch/volume/gap)."""

    def get(self, request):
        try:
            return Response(services.speech_voices())
        except Exception as exc:
            return Response({'voices': [], 'error': str(exc)})


class TranscribeView(APIView):
    """POST multipart `audio` (+ optional `lang`) → {text, language, …}."""
    throttle_scope = 'speech'

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        upload = request.FILES.get('audio')
        if upload is None:
            return Response({'error': 'audio file required'},
                            status=status.HTTP_400_BAD_REQUEST)
        data = upload.read()
        if not data:
            return Response({'error': 'empty audio'}, status=status.HTTP_400_BAD_REQUEST)
        if len(data) > settings.MAX_AUDIO_BYTES:
            return Response({'error': 'audio too large'}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        result = services.transcribe(data, filename=upload.name or 'audio.webm',
                                     language=request.data.get('lang') or None)
        if 'error' in result:
            return Response(result, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(result)


class SynthesizeView(APIView):
    """POST {text, lang} → audio/wav (open-source TTS)."""
    throttle_scope = 'speech'

    def post(self, request):
        text = (request.data.get('text') or '').strip()
        lang = (request.data.get('lang') or 'am').lower()
        if not text:
            return Response({'error': 'text required'}, status=status.HTTP_400_BAD_REQUEST)
        audio, mime, provider = services.synthesize(
            text, lang, **_voice_params(request.data))
        if audio is None:
            return Response({'error': 'text-to-speech unavailable'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        resp = HttpResponse(audio, content_type=mime or 'audio/wav')
        resp['X-TTS-Provider'] = provider or 'unknown'
        return resp


class VoiceTurnView(APIView):
    """One hands-free round trip: audio in → transcript + Zer reply + audio out."""
    throttle_scope = 'voice'

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        upload = request.FILES.get('audio')
        if upload is None:
            return Response({'error': 'audio file required'},
                            status=status.HTTP_400_BAD_REQUEST)
        data = upload.read()
        if not data:
            return Response({'error': 'empty audio'}, status=status.HTTP_400_BAD_REQUEST)
        if len(data) > settings.MAX_AUDIO_BYTES:
            return Response({'error': 'audio too large'}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

        stt = services.transcribe(data, filename=upload.name or 'audio.webm',
                                  language=request.data.get('lang') or None)
        if 'error' in stt:
            return Response({'stage': 'stt', **stt}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        transcript = stt.get('text', '')
        language = stt.get('language') or 'am'
        if not transcript:
            return Response({'transcript': '', 'language': language,
                             'reply': '', 'source': 'empty', 'audio_b64': None})

        history = None
        raw = request.data.get('history')
        if raw:
            try:
                history = json.loads(raw) if isinstance(raw, str) else raw
            except ValueError:
                history = None

        reply = services.chat(transcript, history, lang=language,
                              user=request.user if request.user.is_authenticated else None)
        params = _voice_params(request.data)
        # Per-language voice choice: the language is only known after STT.
        chosen = request.data.get('voice_am' if language == 'am' else 'voice_en')
        if chosen:
            params['voice'] = str(chosen)
        audio, mime, provider = services.synthesize(
            reply.get('reply', ''), language, **params)
        conv_id = _persist_turns(request, transcript, reply.get('reply'), language,
                                 reply.get('source'),
                                 request.data.get('conversation'))

        return Response({
            'transcript': transcript,
            'language': language,
            'language_probability': stt.get('language_probability'),
            'reply': reply.get('reply', ''),
            'source': reply.get('source'),
            'followups': reply.get('followups', []),
            'stt_provider': stt.get('provider'),
            'tts_provider': provider,
            'audio_mime': mime,
            'audio_b64': base64.b64encode(audio).decode('ascii') if audio else None,
            **({'conversation': conv_id} if conv_id else {}),
        })


class HealthView(APIView):
    def get(self, request):
        extra = {}
        try:
            extra['translations'] = services.corrections_count()
        except Exception:
            pass
        return Response({'status': 'ok', 'llm': services.llm_status(), **extra})


_DEV_PAGE = """<!doctype html><html lang="am"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ዘር — API</title>
<style>body{font-family:system-ui,sans-serif;background:#f7f3e9;color:#241f1a;
margin:0;display:grid;place-items:center;min-height:100vh}
main{max-width:640px;padding:32px;background:#fff;border:1px solid #e4dcc8;
border-radius:16px}h1{color:#14532d}code{background:#f0ebdd;padding:2px 6px;border-radius:6px}
a{color:#9c3b1b}</style></head><body><main>
<h1>ዘር (Zer) API ዝግጁ ነው</h1>
<p>The Django REST API is running. The React single-page app has not been built
into <code>backend/static/spa</code> yet.</p>
<p>For development run <code>npm run dev</code> in <code>frontend/</code> (Vite
proxies <code>/api</code> to Django). For production run <code>npm run build</code>.</p>
<p>Try the API: <a href="/api/health">/api/health</a> ·
<a href="/api/llm-status">/api/llm-status</a> ·
<a href="/api/translations/stats">/api/translations/stats</a></p>
</main></body></html>"""


class SpaView(View):
    """Serve the built React app (client-side routing fallback)."""

    def get(self, request):
        index = settings.SPA_DIR / 'index.html'
        if index.exists():
            return HttpResponse(index.read_text(encoding='utf-8'),
                                content_type='text/html; charset=utf-8')
        return HttpResponse(_DEV_PAGE, content_type='text/html; charset=utf-8')


# ---------------------------------------------------------------------------
# PWA root assets (must live at the origin root to scope the service worker)
# ---------------------------------------------------------------------------
_MANIFEST = {
    'name': 'ዘር — Zer · Amharic AI',
    'short_name': 'ዘር',
    'description': 'የአማርኛ AI ረዳት፣ የግዕዝ ኪቦርድና የትርጉም ማስተካከያ።',
    'start_url': '/',
    'scope': '/',
    'display': 'standalone',
    'display_override': ['standalone', 'minimal-ui'],
    'id': '/',
    'orientation': 'any',
    'background_color': '#f7f3e9',
    'theme_color': '#14532d',
    'categories': ['education', 'productivity', 'utilities'],
    'icons': [
        {'src': '/static/spa/icon-192.png', 'sizes': '192x192', 'type': 'image/png'},
        {'src': '/static/spa/icon-512.png', 'sizes': '512x512', 'type': 'image/png',
         'purpose': 'any maskable'},
        {'src': '/static/spa/icon.svg', 'sizes': 'any', 'type': 'image/svg+xml'},
    ],
}


class ManifestView(View):
    def get(self, request):
        return HttpResponse(json.dumps(_MANIFEST, ensure_ascii=False),
                            content_type='application/manifest+json; charset=utf-8')


class ServiceWorkerView(View):
    def get(self, request):
        sw = settings.SPA_DIR / 'sw.js'
        body = sw.read_text(encoding='utf-8') if sw.exists() else '// not built'
        return HttpResponse(
            body,
            content_type='application/javascript; charset=utf-8',
            headers={'Service-Worker-Allowed': '/'},
        )


class RobotsView(View):
    def get(self, request):
        body = ('User-agent: *\nAllow: /\n'
                'Sitemap: https://am-ai.fly.dev/sitemap.xml\n')
        return HttpResponse(body, content_type='text/plain; charset=utf-8')


_PRIVACY = """<!doctype html><html lang="am"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>የግላዊነት መግለጫ · ዘር (Zer)</title>
<style>body{font-family:system-ui,'Noto Sans Ethiopic',sans-serif;background:#f7f3e9;color:#241f1a;
margin:0;padding:40px 18px;line-height:1.7}.p{max-width:720px;margin:0 auto;background:#fffdf7;
border:1px solid #e6ddc8;border-radius:16px;padding:32px}h1{color:#14532d;margin-top:0}
h2{color:#14532d;font-size:1.1rem;margin-bottom:4px}a{color:#9c3b1b}</style></head><body><div class="p">
<h1>የግላዊነት መግለጫ — ዘር (Zer)</h1>
<p>የመጨረሻ ማሻሻያ፦ 2026።</p>
<h2>የምንሰበስበው መረጃ</h2>
<p>ዘር መለያ (account) አስፈላጊ አይደለም። በአንድም መልኩ ሳይገቡ መጠቀም ይችላሉ። ከገቡ ብቻ፣
የውይይት ታሪክዎና የተማሩ እውነታዎች በመለያዎ ላይ ተቀምጠው በሚመለሱበት ጊዜ እንደገና ይጫናሉ። በመለያ
ካልገቡ፣ የእርስዎ ውይይት ከመልስ በኋላ በአገልጋዩ ላይ አይቀመጥም።</p>
<h2>ድምጽ (የዘር የድምጽ ውይይት)</h2>
<p>«ቀጥታ ውይይት»፣ ማይክራፎን ወይም «Hey Zer» ሲጠቀሙ የእርስዎ ድምጽ ወደ አገልጋዩ ተልኮ
በጽሑፍ ይቀየራል (speech-to-text) እና መልሱ በድምጽ ይመለሳል። የድምጽ ቅጂው አይቀመጥም፤
ለውይይት ምላሽ ብቻ ያገለግላል።</p>
<h2>የትርጉም ማስተካከያ</h2>
<p>በ«ትርጉም ማስተካከያ» ገጽ የሚያስተካክሏቸው ትርጉሞች የሁሉም ተጠቃሚዎችን ትርጉም ለማሻሻል ይቀመጣሉ፤
ከግል መለያዎ ጋር አይታሰሩም።</p>
<h2>አገልግሎት ሰጪዎች</h2>
<p>ዘር የራሱን የአማርኛ አእምሮ ይጠቀማል — ውጫዊ AI ሞዴል አያስፈልገውም። አማራጭ የእንግሊዝኛ ትርጉም
ነጻ የማሽን ትርጉም አገልግሎቶችን (MyMemory / Google Translate) ሊጠቀም ይችላል።</p>
<h2>መብቶችዎ</h2>
<p>ማንኛውም ጥያቄ ካለ በGitHub ጉዳይ (issue) ያሳውቁን፦
<a href="https://github.com/ZebraCodeX/amharic-nlp-chatbot">github.com/ZebraCodeX/amharic-nlp-chatbot</a></p>
<p><a href="/">← ወደ መተግበሪያው</a></p></div></body></html>"""


class PrivacyView(View):
    def get(self, request):
        return HttpResponse(_PRIVACY, content_type='text/html; charset=utf-8')
