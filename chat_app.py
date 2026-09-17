#!/usr/bin/env python3
"""
chat_app.py — lightweight HTTP server for the Amharic AI Chat.

Routes:
  GET  /                        → chat.html
  GET/POST  /api/chat           → JSON {reply, source, confidence, elapsed_ms}
                                 (POST body: {text, history?} — best for LLM turns)
  GET  /api/translate?text=&to=en|am  → JSON {translated, score, engine,
                                 verified, reasons, elapsed_ms}
  POST /api/translate/verify    → {text, src, dst, translation, correct?}
                                 saves a user-verified/corrected translation
  GET  /api/translate/review    → recent user corrections for moderation
  GET  /api/translations        → word/translation review catalogue (paginated)
  GET  /api/translations/stats  → counts by review status
  GET  /review                  → translations.html (crowd-correction UI)
  GET  /api/words               → spelling dictionary (data/amharic_words.json)
  GET  /api/ngram               → Amharic n-gram model (Bible-trained, next-word hints)
  GET  /api/suggest?text=…      → type-ahead {words, next, sentences} trained on
                                  books + news articles + movies/web + the Bible
  GET  /api/llm-status          → {available, model?, backend?}
  GET  /api/health              → health check
  GET  /manifest.json           → PWA manifest (mobile install)
  GET  /sw.js                   → service worker (offline cache for the installable app)

Pure stdlib. No dependencies.
"""

import json
import os
import sys
import threading
import time
import socket
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get('PORT', 8080))

templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')


def default_host():
    """Prefer a dual-stack '::' bind when IPv6 is available, so BOTH
    `localhost` (→::1) and the machine's IPv4 address connect. Otherwise
    fall back to plain IPv4 0.0.0.0."""
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        s.bind(('::', 0))
        s.close()
        return '::'
    except (OSError, AttributeError):
        return '0.0.0.0'


HOST = os.environ.get('HOST') or default_host()


class DualStackServer(ThreadingHTTPServer):
    """Threaded HTTPServer that also answers IPv6 (::1 / localhost)."""
    address_family = socket.AF_INET6

    def server_bind(self):
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except (OSError, AttributeError):
            pass
        super().server_bind()


def make_server():
    """Pick the right server class for the configured HOST (threaded)."""
    if HOST == '::':
        return DualStackServer((HOST, PORT), ChatHandler)
    return ThreadingHTTPServer((HOST, PORT), ChatHandler)

assistant = None
_words_cache = None
_ngram_cache = None
_suggest = None
_llm_status = {'available': False, 'model': None, 'backend': None, 'checked': False}
_llm_lock = threading.Lock()
_assistant_lock = threading.RLock()


def get_assistant():
    global assistant
    if assistant is None:
        from chatbot import AmharicAssistant
        assistant = AmharicAssistant()
    return assistant


def get_suggester():
    from amharic_nlp import Suggester
    return Suggester()


def probe_llm():
    """Detect an LLM backend once in the background so first chat isn't slowed."""
    global _llm_status
    try:
        from llm import _configured_backend, _ollama_endpoint
        with _llm_lock:
            if _llm_status['checked']:
                return
            backend = _configured_backend()
            if backend:
                _llm_status = {'available': True, 'model': backend[2],
                               'backend': 'configured', 'checked': True}
                return
            raw = _ollama_endpoint()
            if raw:
                _llm_status = {'available': True, 'model': (raw[3][0] if raw[3] else None),
                               'backend': 'ollama', 'checked': True}
            else:
                _llm_status = {'available': False, 'model': None, 'backend': None, 'checked': True}
    except Exception:
        with _llm_lock:
            _llm_status = {'available': False, 'model': None, 'backend': None, 'checked': True}


class ChatHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')
        qs = parse_qs(parsed.query)

        if path in ('', '/'):
            self._serve_page('chat.html')
        elif path == '/keyboard':
            self._serve_page('keyboard.html')
        elif path == '/review':
            self._serve_page('translations.html')
        elif path.startswith('/static/'):
            self._serve_static(path[len('/static/'):])
        elif path == '/api/chat':
            self._handle_chat(qs)
        elif path == '/api/translate':
            self._handle_translate(qs)
        elif path == '/api/translate/review':
            from translator import corrections_review
            limit_qs = qs.get('limit', ['100'])[0]
            try:
                limit = max(1, min(int(limit_qs), 500))
            except ValueError:
                limit = 100
            items = corrections_review(limit)
            self._json_response({'count': len(items), 'items': items})
        elif path == '/api/translations':
            self._handle_translations(qs)
        elif path == '/api/translations/stats':
            from translator import translation_stats
            self._json_response(translation_stats())
        elif path == '/api/words':
            self._handle_words()
        elif path == '/api/ngram':
            self._handle_ngram()
        elif path == '/api/suggest':
            self._handle_suggest(qs)
        elif path == '/api/llm-status':
            self._json_response(_llm_status)
        elif path == '/api/health':
            try:
                from translator import corrections_count
                extra = {'translations': corrections_count()}
            except Exception:
                extra = {}
            self._json_response({'status': 'ok', **extra})
        elif path == '/manifest.json':
            self._serve_static_file('manifest.json', 'application/manifest+json; charset=utf-8')
        elif path == '/sw.js':
            self._serve_static_file('sw.js', 'application/javascript; charset=utf-8',
                                    extra_headers={'Service-Worker-Allowed': '/'})
        else:
            self._json_response({'error': 'not found'}, code=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')
        if path == '/api/chat':
            self._handle_chat(None)
        elif path in ('/api/translate/verify', '/api/translations/verify'):
            self._handle_translate_verify()
        else:
            self._json_response({'error': 'not found'}, code=404)

    def _serve_page(self, name):
        html_path = os.path.join(templates_dir, name)
        try:
            with open(html_path, encoding='utf-8') as f:
                body = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body.encode('utf-8'))))
            self.end_headers()
            self.wfile.write(body.encode('utf-8'))
        except FileNotFoundError:
            self._json_response({'error': f'{name} not found'}, code=500)

    _MIME = {
        '.js': 'application/javascript; charset=utf-8',
        '.css': 'text/css; charset=utf-8',
        '.html': 'text/html; charset=utf-8',
        '.json': 'application/json; charset=utf-8',
        '.svg': 'image/svg+xml',
        '.png': 'image/png',
        '.woff2': 'font/woff2',
    }

    def _serve_static(self, rel):
        self._serve_static_file(rel)

    def _serve_static_file(self, rel, forced_mime=None, extra_headers=None):
        safe = os.path.normpath(rel)
        if safe.startswith('..') or os.path.isabs(safe):
            self._json_response({'error': 'forbidden'}, code=403)
            return
        path = os.path.join(static_dir, safe)
        try:
            with open(path, 'rb') as f:
                body = f.read()
        except (OSError, FileNotFoundError):
            self._json_response({'error': 'not found'}, code=404)
            return
        ctype = forced_mime
        if ctype is None:
            ctype = 'application/octet-stream'
            for ext, mime in self._MIME.items():
                if path.endswith(ext):
                    ctype = mime
                    break
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self, limit=1 << 20):
        try:
            n = int(self.headers.get('Content-Length', 0))
        except (TypeError, ValueError):
            n = 0
        if n <= 0 or n > limit:
            return None
        try:
            return json.loads(self.rfile.read(n))
        except Exception:
            return None

    def _handle_chat(self, qs):
        history = None
        if qs is None:
            body = self._read_body()
            if body and isinstance(body, dict):
                text = (body.get('text') or '').strip()
                history = body.get('history')
            else:
                self._json_response({'error': 'bad request'}, code=400)
                return
        else:
            text = qs.get('text', [''])[0].strip()
            raw = qs.get('history', [''])[0].strip()
            if raw:
                try:
                    history = json.loads(raw)
                except ValueError:
                    history = None
        if not text:
            self._json_response({'reply': 'ምን ትፈልጋለህ? በአማርኛ ጻፍልኝ.', 'source': 'empty', 'confidence': 0.0})
            return
        a = get_assistant()
        # The assistant keeps a small context window. Serialize assignment and
        # response so concurrent browser/mobile requests cannot interleave turns.
        with _assistant_lock:
            if isinstance(history, list):
                from chatbot import normalize_history
                norm = normalize_history(history)
                # drop trailing turns that duplicate the message being sent now
                while norm and norm[-1].get('user') == text:
                    norm.pop()
                a.history = norm[:10]
            start = time.time()
            result = a.respond(text)
        result['elapsed_ms'] = round((time.time() - start) * 1000)
        self._json_response(result)

    def _handle_translate(self, qs):
        text = qs.get('text', [''])[0].strip()
        to = qs.get('to', ['en'])[0].lower()
        if not text:
            self._json_response({'translated': '', 'error': 'empty'})
            return
        from translator import best_translate
        src = 'am' if to != 'am' else 'en'
        start = time.time()
        result = best_translate(text, src, to)
        result['src'] = src
        result['to'] = to
        result['elapsed_ms'] = round((time.time() - start) * 1000)
        self._json_response(result)

    def _handle_translate_verify(self):
        body = self._read_body()
        if not body or not isinstance(body, dict):
            self._json_response({'error': 'bad request'}, code=400)
            return
        from translator import store_verification
        text = (body.get('text') or '').strip()
        translation = (body.get('translation') or '').strip()
        raw_correction = body.get('correct')
        correction = raw_correction.strip() if isinstance(raw_correction, str) else ''
        src = body.get('src') or ('am' if body.get('dst') != 'am' else 'en')
        dst = body.get('dst') or 'en'
        if not text or (not translation and not correction):
            self._json_response({'error': 'text and translation required'}, code=400)
            return
        rec = store_verification(text, src, dst, translation or correction,
                                 correction=correction, engine=body.get('engine') or 'user')
        if rec is None:
            self._json_response({'error': 'could not save'}, code=500)
            return
        self._json_response({
            'ok': True,
            'id': rec['id'],
            'corrected': rec['corrected'],
            'endorsed': rec.get('endorsed', 0),
        })

    def _handle_translations(self, qs):
        """Paginated Amharic↔English review catalogue for the /review UI."""
        from translator import list_translations
        q = qs.get('q', [''])[0]
        status = qs.get('status', ['review'])[0].lower()
        limit = qs.get('limit', ['100'])[0]
        offset = qs.get('offset', ['0'])[0]
        max_conf = qs.get('max_confidence', [None])[0]
        self._json_response(list_translations(query=q, status=status,
                                              limit=limit, offset=offset,
                                              max_confidence=max_conf))

    def _handle_words(self):
        global _words_cache
        if _words_cache is None:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'amharic_words.json')
            try:
                with open(path, encoding='utf-8') as f:
                    _words_cache = json.load(f)
            except FileNotFoundError:
                _words_cache = {'words': []}
        self._json_response(_words_cache)

    def _handle_ngram(self):
        global _ngram_cache
        if _ngram_cache is None:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'nl_model.json')
            try:
                with open(path, encoding='utf-8') as f:
                    _ngram_cache = json.load(f)
            except FileNotFoundError:
                _ngram_cache = {'unigram': {}, 'bigram': {}, 'trigram': {}, 'starters': {}}
        self._json_response(_ngram_cache)

    def _handle_suggest(self, qs):
        """Type-ahead: nearest words + next-word hints + sentence completions."""
        global _suggest
        if _suggest is None:
            _suggest = get_suggester()
        text = qs.get('text', [''])[0].strip()
        start = time.time()
        result = _suggest.suggest(text)
        result['elapsed_ms'] = round((time.time() - start) * 1000)
        self._json_response(result)

    def _json_response(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        ts = time.strftime('%H:%M:%S')
        sys.stderr.write(f'[{ts}] {args[0]}\n')


def main():
    print('Loading ሕሳር (Amharic AI)…')
    get_assistant()
    threading.Thread(target=probe_llm, daemon=True).start()
    server = make_server()
    port = server.server_address[1]
    print(f'Amharic AI Chat running on:\n  http://localhost:{port}  (this machine)')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down.')
        server.server_close()


if __name__ == '__main__':
    main()
