#!/usr/bin/env python3
"""
chat_app.py — lightweight HTTP server for the Amharic AI Chat.

Routes:
  GET  /            → chat.html
  GET  /api/chat    → JSON {reply, source, confidence}
  GET  /api/health  → health check

Pure stdlib. No dependencies.
"""

import json
import os
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get('PORT', 8080))
HOST = os.environ.get('HOST', '0.0.0.0')

templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
assistant = None


def get_assistant():
    global assistant
    if assistant is None:
        from chatbot import AmharicAssistant
        assistant = AmharicAssistant()
    return assistant


class ChatHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')
        qs = parse_qs(parsed.query)

        if path in ('', '/'):
            self._serve_chat_html()
        elif path == '/api/chat':
            self._handle_chat(qs)
        elif path == '/api/health':
            self._json_response({'status': 'ok'}, code=200)
        else:
            self._json_response({'error': 'not found'}, code=404)

    def _serve_chat_html(self):
        html_path = os.path.join(templates_dir, 'chat.html')
        try:
            with open(html_path, encoding='utf-8') as f:
                body = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body.encode('utf-8'))))
            self.end_headers()
            self.wfile.write(body.encode('utf-8'))
        except FileNotFoundError:
            self._json_response({'error': 'chat.html not found'}, code=500)

    def _handle_chat(self, qs):
        text = qs.get('text', [''])[0].strip()
        if not text:
            self._json_response({'reply': 'ምን ትፈልጋለህ? በአማርኛ ጻፍልኝ.', 'source': 'empty', 'confidence': 0.0})
            return
        a = get_assistant()
        start = time.time()
        result = a.respond(text)
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
    print(f'Amharic AI Chat running on http://{HOST}:{PORT}')
    server = HTTPServer((HOST, PORT), ChatHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down.')
        server.server_close()


if __name__ == '__main__':
    main()
