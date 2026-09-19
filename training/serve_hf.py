#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
serve_hf.py — tiny OpenAI-compatible server for a merged Zer model.

vLLM is great but heavy; on a 6 GB GPU (or CPU-only) this serves the merged
model with plain `transformers` — the same stack the trainer already installed —
and exposes just the two endpoints `llm.py` uses: GET /v1/models and
POST /v1/chat/completions. Optional bearer-token auth.

    python training/serve_hf.py --model training/out/zer-lora-merged \
        --api-key "$(openssl rand -hex 20)" --port 8000

Pair it with a tunnel and point the app at it (see training/connect-fly.sh):

    LLM_BASE_URL=https://YOUR-URL/v1 LLM_MODEL=zer LLM_API_KEY=… \
      bash training/connect-fly.sh

Only for single-user / low-traffic use; use vLLM (training/serve.sh) when you
need real concurrency.
"""
import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import hf_transfer  # noqa: F401
except ImportError:
    os.environ.pop('HF_HUB_ENABLE_HF_TRANSFER', None)

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

STATE = {}


def load_model(model_id, max_model_len):
    tok = AutoTokenizer.from_pretrained(model_id)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = AutoModelForCausalLM.from_pretrained(model_id, dtype=dtype)
    model.eval().to(device)
    STATE.update(tok=tok, model=model, device=device, max_model_len=max_model_len)
    print(f'loaded {model_id} on {device} ({dtype})')


def render(tok, messages):
    if getattr(tok, 'chat_template', None):
        return tok.apply_chat_template(messages, tokenize=False,
                                       add_generation_prompt=True)
    system = next((m['content'] for m in messages if m['role'] == 'system'), '')
    user = next((m['content'] for m in messages if m['role'] == 'user'), '')
    return f"### System\n{system}\n### User\n{user}\n### Assistant\n"


def complete(messages, max_tokens, temperature, top_p):
    tok, model, device = STATE['tok'], STATE['model'], STATE['device']
    text = render(tok, messages)
    ids = tok(text, add_special_tokens=False)['input_ids']
    ids = ids[-STATE['max_model_len']:]
    input_ids = torch.tensor([ids], device=device)
    params = dict(max_new_tokens=max_tokens, pad_token_id=tok.eos_token_id)
    if temperature and temperature > 0:
        params.update(do_sample=True, temperature=temperature, top_p=top_p)
    else:
        params.update(do_sample=False)
    with torch.no_grad():
        out = model.generate(input_ids=input_ids,
                             attention_mask=torch.ones_like(input_ids), **params)
    new_ids = out[0][input_ids.shape[1]:]
    return tok.decode(new_ids, skip_special_tokens=True).strip(), len(new_ids)


class Handler(BaseHTTPRequestHandler):
    server_version = 'ZerHF/1.0'

    def log_message(self, fmt, *args):
        print(f'{self.address_string()} - {fmt % args}', flush=True)

    def _auth_ok(self):
        key = STATE['api_key']
        if not key:
            return True
        header = self.headers.get('Authorization', '')
        return header == f'Bearer {key}'

    def _json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip('/') in ('/v1/models', '/models'):
            if not self._auth_ok():
                return self._json(401, {'error': {'message': 'invalid api key'}})
            return self._json(200, {
                'object': 'list',
                'data': [{'id': STATE['name'], 'object': 'model',
                          'owned_by': 'zer', 'created': int(time.time())}],
            })
        if self.path.rstrip('/') in ('/health', '/'):
            return self._json(200, {'status': 'ok', 'model': STATE['name']})
        return self._json(404, {'error': {'message': 'not found'}})

    def do_POST(self):
        if self.path.rstrip('/') != '/v1/chat/completions':
            return self._json(404, {'error': {'message': 'not found'}})
        if not self._auth_ok():
            return self._json(401, {'error': {'message': 'invalid api key'}})
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length) or b'{}')
        except (ValueError, OSError):
            return self._json(400, {'error': {'message': 'bad json'}})

        messages = body.get('messages') or []
        if not messages:
            return self._json(400, {'error': {'message': 'messages required'}})
        max_tokens = min(int(body.get('max_tokens') or 512), 1024)
        temperature = float(body.get('temperature', 0.0) or 0.0)
        top_p = float(body.get('top_p', 0.9) or 0.9)

        try:
            reply, n = complete(messages, max_tokens, temperature, top_p)
        except Exception as exc:  # pragma: no cover
            return self._json(500, {'error': {'message': str(exc)}})

        return self._json(200, {
            'id': f'chatcmpl-{int(time.time() * 1000)}',
            'object': 'chat.completion',
            'created': int(time.time()),
            'model': body.get('model') or STATE['name'],
            'choices': [{'index': 0, 'finish_reason': 'stop',
                         'message': {'role': 'assistant', 'content': reply}}],
            'usage': {'completion_tokens': n},
        })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', required=True)
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--api-key', default=os.environ.get('LLM_API_KEY', ''))
    ap.add_argument('--served-name', default='zer')
    ap.add_argument('--max-model-len', type=int, default=2048)
    args = ap.parse_args()

    STATE.update(api_key=args.api_key, name=args.served_name)
    load_model(args.model, args.max_model_len)

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'serving "{args.served_name}" on http://{args.host}:{args.port}/v1 '
          f'(api_key {"set" if args.api_key else "open"})', flush=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == '__main__':
    main()
