#!/usr/bin/env python3
"""
llm.py — keyless, configurable LLM client for ሕሳር.

The assistant becomes a real LLM whenever ANY backend is reachable. Priority
when picking a backend:

  1. The embedded Zer model (zer_model.py — the fine-tuned Qwen GGUF loaded
     in-process through llama.cpp). This is the default: the deployed app is
     self-contained and never calls an external inference host.
  2. $LLM_BASE_URL / $LLM_API_KEY / $LLM_MODEL  (explicit config, e.g. point it
     at any OpenAI, OpenRouter, Groq, Together… endpoint). Only used when the
     embedded model is unavailable, or when ZER_LLM_BACKEND=remote is set.
  3. $OPENAI_API_KEY + optional $OPENAI_BASE_URL (classic OpenAI)
  4. A local Ollama server at http://localhost:11434  (auto-detected)

To go "full LLM" on this machine with the embedded model:
    pip install llama-cpp-python
    python3 chat_app.py        # loads models/zer-qwen-q4_k_m.gguf automatically

Or with a remote OpenAI-compatible endpoint:
    LLM_BASE_URL=https://api.groq.com/openai/v1 \
    LLM_API_KEY=… LLM_MODEL=llama-3.3-70b-versatile python3 chat_app.py

When no backend is reachable the engine silently falls back to the local
rule-based brain — the chat keeps working offline.

Pure stdlib. No dependencies.
"""

import hashlib
import json
import os
import re
import threading
import urllib.request
import urllib.error
import urllib.parse

_TIMEOUT = float(os.environ.get('LLM_TIMEOUT', '80'))
_MAX_TOKENS = int(os.environ.get('LLM_MAX_TOKENS', '1200'))

_cache = {}
_cache_lock = threading.Lock()
_detect_lock = threading.RLock()
_detected = None

_embedded_cached = None
_embedded_lock = threading.RLock()


def _embedded_available():
    """The in-process Zer engine is usable (file present + llama.cpp installed)."""
    global _embedded_cached
    with _embedded_lock:
        if _embedded_cached is None:
            try:
                import zer_model
                probe = getattr(zer_model, 'available_any', None)
                _embedded_cached = bool(probe()) if probe else bool(zer_model.available())
            except Exception:
                _embedded_cached = False
        return _embedded_cached


def _embedded_backend_info():
    try:
        import zer_model
        st = zer_model.status()
        return (True, st.get('model') or 'zer-embedded')
    except Exception:
        return (False, None)


def _grounding_on():
    return os.environ.get('ZER_GROUNDING', '1').strip().lower() not in (
        '0', 'off', 'false', 'no')


def _grounded_system(system, user, lang):
    """Append facts retrieved from Zer's own local data, when any match.

    This is what lets a small embedded model answer its own domain correctly
    without any external service: the lookup happens entirely on this machine.
    """
    if not _grounding_on() or not user:
        return system
    try:
        import grounding
        ctx = grounding.context(user, lang=lang)
    except Exception:
        return system
    return f'{system}\n\n{ctx}' if ctx else system


def _post_json(url, payload, timeout, api_key=None):
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'Hisar-Amharic-AI/1.0',
    }
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode('utf-8', 'replace')


def _get_json(url, timeout):
    req = urllib.request.Request(url, headers={'User-Agent': 'Hisar-Amharic-AI/1.0'}, method='GET')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode('utf-8', 'replace')


def _configured_backend():
    base = os.environ.get('LLM_BASE_URL') or os.environ.get('OPENAI_BASE_URL')
    key = os.environ.get('LLM_API_KEY') or os.environ.get('OPENAI_API_KEY', '')
    model = os.environ.get('LLM_MODEL')
    if base:
        return (base.rstrip('/') + '/chat/completions', key, model)
    if key:
        return ('https://api.openai.com/v1/chat/completions', key, model or 'gpt-4o-mini')
    return None


def _ollama_endpoint():
    global _detected
    with _detect_lock:
        if _detected is not None:
            return _detected
        try:
            raw = _get_json('http://localhost:11434/api/tags', 2.0)
            models = [m['name'] for m in json.loads(raw).get('models', [])]
            if models:
                _detected = ('http://localhost:11434/v1/chat/completions', '', None, models)
                return _detected
        except Exception:
            pass
        _detected = False
        return False


def _prefer_remote():
    """Explicit opt-out of the embedded model.

    The bundled, fine-tuned Zer GGUF is used by default so the deployed app is
    fully self-contained and never phones home to an external inference host.
    Setting ZER_LLM_BACKEND=remote restores the old "configured endpoint first"
    ordering for local experimentation.
    """
    return os.environ.get('ZER_LLM_BACKEND', 'auto').strip().lower() in (
        'remote', 'api', 'external', 'http')


def _resolve_backend():
    """Pick the backend to use, as ``(kind, backend)``.

    Default order: embedded (trained local model) → remote (LLM_BASE_URL) →
    local Ollama. This guarantees the shipped app runs the model that is baked
    into the image instead of an external Hugging Face / cloud endpoint.
    """
    configured = _configured_backend()
    if _prefer_remote() and configured:
        return 'remote', configured
    if _embedded_available():
        return 'embedded', None
    if configured:
        return 'remote', configured
    ollama = _ollama_endpoint()
    if ollama:
        return 'ollama', ollama
    return None, None


def available():
    """"True if an LLM backend (embedded, explicit config or local Ollama) is reachable."""
    kind, _ = _resolve_backend()
    return kind is not None


def which():
    """Return (backend, model) for status pages, in priority order."""
    kind, backend = _resolve_backend()
    if kind == 'embedded':
        _, model = _embedded_backend_info()
        return ('embedded', model)
    if kind == 'remote':
        return ('configured', backend[2] or 'gpt-4o-mini')
    if kind == 'ollama':
        return ('ollama', (backend[3][0] if backend[3] else None))
    return (None, None)


def _pick_model(model, available_models):
    if model:
        return model
    if not available_models:
        return None
    for pref in ('qwen', 'llama', 'gemma', 'mistral', 'aya'):
        for m in available_models:
            if pref in m.lower():
                return m
    return available_models[0]


def _build_messages(system, user, history):
    messages = [{'role': 'system', 'content': system}]
    for turn in (history or [])[-6:]:
        if isinstance(turn, dict) and 'role' in turn and 'content' in turn:
            messages.append({'role': turn['role'], 'content': str(turn['content'])[:4000]})
    messages.append({'role': 'user', 'content': user})
    return messages


def chat(system, user, history=None, model=None, max_tokens=_MAX_TOKENS, timeout=_TIMEOUT,
         lang=None):
    """
    Send a chat request to the best reachable backend. Returns the text reply
    or None if no backend responded (caller falls back to the rule engine).

    ``lang`` selects the embedded engine (``en`` → base Qwen, otherwise the
    Amharic fine-tune); it is ignored by the remote/Ollama backends.
    """
    kind, backend = _resolve_backend()
    avail_models = None
    if kind == 'embedded':
        import zer_model
        # Detailed answers are expected; cap guards CPU latency.
        cap = int(os.environ.get('LLM_MAX_TOKENS', '768'))
        system = _grounded_system(system, user, lang)
        payload_cache_key = hashlib.sha1(json.dumps(
            [lang, _build_messages(system, user, history), max_tokens],
            ensure_ascii=False).encode('utf-8')).hexdigest()
        with _cache_lock:
            if payload_cache_key in _cache:
                return _cache[payload_cache_key]
        reply = zer_model.chat(system, user, history, model=model,
                               max_tokens=min(max_tokens, cap), lang=lang)
        if reply:
            with _cache_lock:
                if len(_cache) < 200:
                    _cache[payload_cache_key] = reply
        return reply
    if kind == 'ollama':
        url, key, cfg_model, avail_models = backend
    elif kind == 'remote':
        url, key, cfg_model = backend
    else:
        return None

    messages = _build_messages(system, user, history)

    payload = {
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': float(os.environ.get('LLM_TEMPERATURE', '0.9')),
    }
    chosen = _pick_model(model or cfg_model, avail_models)
    if chosen:
        payload['model'] = chosen

    cache_key = hashlib.sha1(json.dumps(payload, ensure_ascii=False).encode('utf-8')).hexdigest()
    with _cache_lock:
        if cache_key in _cache:
            return _cache[cache_key]

    try:
        raw = _post_json(url, payload, timeout, api_key=key)
        data = json.loads(raw)
        reply = data['choices'][0]['message']['content'].strip()
    except Exception:
        return None
    if not reply:
        return None

    with _cache_lock:
        if len(_cache) < 200:
            _cache[cache_key] = reply
    return reply


def chat_stream(system, user, history=None, model=None, max_tokens=None,
                timeout=_TIMEOUT, lang=None):
    """Yield reply text deltas from the best reachable backend (no blocking wait).

    Backend priority mirrors :func:`chat`. Yields nothing when no backend
    responds (caller falls back to the rule engine / creative skills).
    """
    kind, backend = _resolve_backend()
    avail_models = None
    if kind == 'embedded':
        import zer_model
        cap = int(os.environ.get('LLM_MAX_TOKENS', '768'))
        system = _grounded_system(system, user, lang)
        for delta in zer_model.chat_stream(
                system, user, history, model=model,
                max_tokens=min(max_tokens or cap, cap), lang=lang):
            if delta:
                yield delta
        return
    if kind == 'ollama':
        url, key, cfg_model, avail_models = backend
    elif kind == 'remote':
        url, key, cfg_model = backend
    else:
        return

    messages = _build_messages(system, user, history)
    payload = {
        'messages': messages,
        'max_tokens': max_tokens or int(os.environ.get('LLM_MAX_TOKENS', '1200')),
        'temperature': float(os.environ.get('LLM_TEMPERATURE', '0.9')),
        'stream': True,
    }
    chosen = _pick_model(model or cfg_model, avail_models)
    if chosen:
        payload['model'] = chosen

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
        'User-Agent': 'Hisar-Amharic-AI/1.0',
    }
    if key:
        headers['Authorization'] = f'Bearer {key}'
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode('utf-8', 'replace').strip()
                if not line.startswith('data:'):
                    continue
                data = line[5:].strip()
                if data == '[DONE]':
                    break
                try:
                    delta = json.loads(data)['choices'][0]['delta'].get('content')
                except Exception:
                    continue
                if delta:
                    yield delta
    except Exception:
        return


def clear_cache():
    with _cache_lock:
        _cache.clear()
