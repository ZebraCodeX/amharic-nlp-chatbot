#!/usr/bin/env python3
"""
llm.py — keyless, configurable LLM client for ሕሳር.

The assistant becomes a real LLM whenever ANY OpenAI-compatible endpoint is
reachable. Priority when picking a backend:

  1. $LLM_BASE_URL / $LLM_API_KEY / $LLM_MODEL  (explicit config,
     e.g. point it at any OpenAI, OpenRouter, Groq, Together… endpoint)
  2. $OPENAI_API_KEY + optional $OPENAI_BASE_URL (classic OpenAI)
  3. A local Ollama server at http://localhost:11434  (auto-detected)

To go "full LLM" on this machine:
    curl -fsSL https://ollama.com/install.sh | sh
    ollama pull qwen3:1.7b        # or gemma2:2b, llama3.2:1b, …

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


def available():
    """"True if an LLM backend (explicit config or local Ollama) is reachable."""
    if _configured_backend():
        return True
    return bool(_ollama_endpoint())


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


def chat(system, user, history=None, model=None, max_tokens=_MAX_TOKENS, timeout=_TIMEOUT):
    """
    Send a chat request to the best reachable backend. Returns the text reply
    or None if no backend responded (caller falls back to the rule engine).
    """
    backend = _configured_backend()
    avail_models = None
    if not backend:
        ollama = _ollama_endpoint()
        if not ollama:
            return None
        backend = ollama[0], '', None
        avail_models = ollama[3]
    url, key, cfg_model = backend

    messages = [{'role': 'system', 'content': system}]
    for turn in (history or [])[-6:]:
        if isinstance(turn, dict) and 'role' in turn and 'content' in turn:
            messages.append({'role': turn['role'], 'content': str(turn['content'])[:4000]})
    messages.append({'role': 'user', 'content': user})

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


def clear_cache():
    with _cache_lock:
        _cache.clear()
