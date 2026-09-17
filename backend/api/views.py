"""REST API views (DRF) wrapping the pure-stdlib NLP services."""
import json

from django.conf import settings
from django.http import HttpResponse
from django.views import View
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import (
    ChatRequestSerializer,
    TranslateQuerySerializer,
    VerifySerializer,
)


def _int_param(request, name, default, lo, hi):
    try:
        return max(lo, min(int(request.query_params.get(name, default)), hi))
    except (TypeError, ValueError):
        return default


class ChatView(APIView):
    """POST {text, history?} or GET ?text=&history= → the assistant's reply."""

    def post(self, request):
        ser = ChatRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = services.chat(ser.validated_data['text'],
                               ser.validated_data.get('history'))
        return Response(result)

    def get(self, request):
        history = None
        raw = request.query_params.get('history')
        if raw:
            try:
                history = json.loads(raw)
            except ValueError:
                history = None
        return Response(services.chat(request.query_params.get('text', ''), history))


class TranslateView(APIView):
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
        ))


class TranslationStatsView(APIView):
    def get(self, request):
        return Response(services.translation_stats())


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
        return Response(services.words())


class NgramView(APIView):
    def get(self, request):
        return Response(services.ngram())


class SuggestView(APIView):
    def get(self, request):
        return Response(services.suggest(request.query_params.get('text', '')))


class LlmStatusView(APIView):
    def get(self, request):
        return Response(services.llm_status())


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
<title>ሕሳር — API</title>
<style>body{font-family:system-ui,sans-serif;background:#f7f3e9;color:#241f1a;
margin:0;display:grid;place-items:center;min-height:100vh}
main{max-width:640px;padding:32px;background:#fff;border:1px solid #e4dcc8;
border-radius:16px}h1{color:#14532d}code{background:#f0ebdd;padding:2px 6px;border-radius:6px}
a{color:#9c3b1b}</style></head><body><main>
<h1>ሕሳር API ዝግጁ ነው</h1>
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
    'name': 'ሕሳር — Amharic AI',
    'short_name': 'ሕሳር',
    'description': 'የአማርኛ AI ረዳት፣ የግዕዝ ኪቦርድና የትርጉም ማስተካከያ።',
    'start_url': '/',
    'scope': '/',
    'display': 'standalone',
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
        if not sw.exists():
            return HttpResponse('// not built', content_type='application/javascript')
        return HttpResponse(sw.read_text(encoding='utf-8'),
                            content_type='application/javascript; charset=utf-8',
                            headers={'Service-Worker-Allowed': '/'})


class RobotsView(View):
    def get(self, request):
        body = ('User-agent: *\nAllow: /\n'
                'Sitemap: https://hisar-amharic-ai.fly.dev/sitemap.xml\n')
        return HttpResponse(body, content_type='text/plain; charset=utf-8')


_PRIVACY = """<!doctype html><html lang="am"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>የግላዊነት መግለጫ · ሕሳር</title>
<style>body{font-family:system-ui,'Noto Sans Ethiopic',sans-serif;background:#f7f3e9;color:#241f1a;
margin:0;padding:40px 18px;line-height:1.7}.p{max-width:720px;margin:0 auto;background:#fffdf7;
border:1px solid #e6ddc8;border-radius:16px;padding:32px}h1{color:#14532d;margin-top:0}
h2{color:#14532d;font-size:1.1rem;margin-bottom:4px}a{color:#9c3b1b}</style></head><body><div class="p">
<h1>የግላዊነት መግለጫ — ሕሳር (Amharic AI)</h1>
<p>የመጨረሻ ማሻሻያ፦ 2026።</p>
<h2>የምንሰበስበው መረጃ</h2>
<p>ሕሳር መለያ (account) አይጠይቅም። የምትልካቸው መልእክቶች ለAI ምላሽ ብቻ ያገለግላሉ። የመልእክት ታሪክ
በአገልጋዩ ላይ አይቀመጥም።</p>
<h2>የትርጉም ማስተካከያ</h2>
<p>በ«ትርጉም ማስተካከያ» ገጽ የምታስተካክላቸው ትርጉሞች የሁሉም ተጠቃሚዎችን ትርጉም ለማሻሻል ይቀመጣሉ፤
ከግል መረጃ ጋር አይታሰሩም።</p>
<h2>አገልግሎት ሰጪዎች</h2>
<p>አማራጭ የእንግሊዝኛ ትርጉም ነጻ የማሽን ትርጉም አገልግሎቶችን (MyMemory / Google Translate)
ሊጠቀም ይችላል። AI ምላሾች በራሳቸው አምራች (generative) ሞዴሎች ሊሰጡ ይችላሉ።</p>
<h2>መብቶችህ</h2>
<p>ማንኛውም ጥያቄ ካለህ በGitHub ጉዳይ (issue) አሳውቀን፦
<a href="https://github.com/ZebraCodeX/amharic-nlp-chatbot">github.com/ZebraCodeX/amharic-nlp-chatbot</a></p>
<p><a href="/">← ወደ መተግበሪያው</a></p></div></body></html>"""


class PrivacyView(View):
    def get(self, request):
        return HttpResponse(_PRIVACY, content_type='text/html; charset=utf-8')
