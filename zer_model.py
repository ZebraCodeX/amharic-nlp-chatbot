#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zer_model.py — the embedded Zer model framework (bilingual, two engines).

The deployed app is self-contained: it loads and runs its models itself through
llama.cpp — no external GPU host, no network round-trip, no API key.

Two engines are supported, selected by language:

  * **Amharic** (`am`) — the fine-tuned Zer GGUF (QLoRA Qwen2.5-1.5B merged),
    which is strongest for Amharic. Default file:
    ``models/zer-qwen-q4_k_m.gguf`` (env ``ZER_MODEL``).
  * **English** (`en`) — a coherent base Qwen2.5-1.5B-Instruct GGUF, because the
    Amharic adapter degrades open-ended English. Default file:
    ``models/qwen2.5-1.5b-instruct-q4_k_m.gguf`` (env ``ZER_MODEL_EN``).

    ZER_MODEL / ZER_MODEL_EN   paths to the .gguf files
    ZER_THREADS   CPU threads for inference (default: min(8, cpu_count))
    ZER_CTX       context length in tokens  (default 1024)
    ZER_BATCH     prompt batch tokens       (default 512 — faster prefill)
    ZER_MAX_TOKENS default reply cap        (default 768)

Engines are lazy: the first import starts a background warm-up of the Amharic
model so a request never pays the full load; the English model loads on first
use. ``load()`` blocks until ready (or returns False when llama-cpp-python or
the model file is missing — the app then falls back to the rule brain).

Usage:

    import zer_model
    zer_model.load('am')                       # warm-up (blocks until ready)
    zer_model.available('en')                  # is that engine reachable?
    zer_model.chat(system, user, history, lang='en')   # one full reply
    for delta in zer_model.chat_stream(..., lang='am'):  # …or token-by-token

Thread-safety: generation is serialized with a lock (llama.cpp context objects
are not safe for concurrent sampling), so concurrent Django/gunicorn threads
queue cleanly instead of corrupting state.
"""

import os
import threading
import time

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_AM = os.path.join(REPO_ROOT, 'models', 'zer-qwen-q4_k_m.gguf')
DEFAULT_EN = os.path.join(REPO_ROOT, 'models', 'qwen2.5-1.5b-instruct-q4_k_m.gguf')

MODEL_NAME = 'zer-embedded'
MAX_TOKENS = int(os.environ.get('ZER_MAX_TOKENS', '768'))

_LANGS = ('am', 'en')
_llms = {}                 # lang -> Llama
_states = {k: 'idle' for k in _LANGS}
_errors = {k: None for k in _LANGS}
_load_locks = {k: threading.RLock() for k in _LANGS}
_gen_lock = threading.Lock()

# llama.cpp ack — cached so `available()` stays cheap at probe time.
_llama_cls = None
_llama_cls_lock = threading.Lock()
_error_msgs = []


def _lang_key(lang):
    return 'en' if str(lang or '').lower().startswith('en') else 'am'


def _model_path(lang):
    key = _lang_key(lang)
    if key == 'en':
        return os.environ.get('ZER_MODEL_EN') or DEFAULT_EN
    return os.environ.get('ZER_MODEL') or DEFAULT_AM


def _llama():
    """Import the llama_cpp.Llama class once; None when not installed."""
    global _llama_cls
    with _llama_cls_lock:
        if _llama_cls is None:
            try:
                from llama_cpp import Llama
                _llama_cls = Llama
            except Exception as exc:  # pragma: no cover - environment dependent
                _llama_cls = False
                _error_msgs.append(f'no llama_cpp: {exc}'.replace('\n', ' '))
    return _llama_cls


def _config():
    n_threads = int(os.environ.get('ZER_THREADS', '0'))
    if n_threads <= 0:
        n_threads = min(8, os.cpu_count() or 4)
    return {
        'n_ctx': max(256, int(os.environ.get('ZER_CTX', '1024'))),
        'n_batch': max(32, int(os.environ.get('ZER_BATCH', '512'))),
        'n_threads': n_threads,
    }


def model_file(lang='am'):
    """Absolute path of the GGUF file this language would load."""
    return _model_path(lang)


def file_available(lang='am'):
    path = _model_path(lang)
    return bool(path) and os.path.exists(path)


def load(lang='am', wait=True):
    """Load a language's model into memory. Thread-safe; idempotent.

    Returns True once ready. Returns False quickly when llama-cpp-python is
    missing or the GGUF file is absent (the app keeps working offline).
    """
    key = _lang_key(lang)
    with _load_locks[key]:
        if _llms.get(key) is not None:
            return True
        path = _model_path(key)
        if not path or not os.path.exists(path):
            _states[key], _errors[key] = 'error', 'model file not found: %s' % path
            return False
        Llama = _llama()
        if not Llama:
            _states[key] = 'error'
            _errors[key] = _error_msgs[-1] if _error_msgs else 'llama_cpp missing'
            return False
        _states[key] = 'loading'
        cfg = _config()
        try:
            _llms[key] = Llama(
                model_path=path,
                n_ctx=cfg['n_ctx'],
                n_batch=cfg['n_batch'],
                n_threads=cfg['n_threads'],
                verbose=False,
                use_mmap=True,
            )
            _states[key] = 'ready'
        except Exception as exc:  # pragma: no cover - model/env dependent
            _llms.pop(key, None)
            _states[key] = 'error'
            _errors[key] = str(exc).replace('\n', ' ')
            return False
        return True


def warm(lang='am'):
    """Start an eager background warm-up (non-blocking)."""
    if lang is True or lang is None:
        lang = 'am'
    thread = threading.Thread(target=load, args=(lang,), name=f'zer-model-warm-{lang}',
                              daemon=True)
    thread.start()
    return thread


def available(lang='am'):
    """True when a functional engine will be available for that language."""
    key = _lang_key(lang)
    with _load_locks[key]:
        if _llms.get(key) is not None:
            return True
    if not file_available(key):
        return False
    return bool(_llama())


def available_any():
    return any(available(k) for k in _LANGS)


def _engine_status(key):
    return {
        'available': available(key),
        'model': os.path.basename(_model_path(key)) if file_available(key) else None,
        'file': _model_path(key) if file_available(key) else None,
        'state': _states.get(key),
        'loaded': _llms.get(key) is not None,
        'error': _errors.get(key),
    }


def status():
    """Stable status dict for /api/llm-status and the help page."""
    am = _engine_status('am')
    en = _engine_status('en')
    return {
        'available': available_any(),
        'backend': 'embedded',
        'model': am['model'],
        'state': am['state'],
        'loaded': am['loaded'],
        'file': am['file'],
        'error': am['error'],
        'models': {'am': am, 'en': en},
    }


def _messages(system, user, history):
    msgs = []
    if system:
        msgs.append({'role': 'system', 'content': system})
    for turn in (history or [])[-6:]:
        if isinstance(turn, dict) and 'role' in turn and 'content' in turn:
            msgs.append({'role': str(turn['role']), 'content': str(turn['content'])[:4000]})
    msgs.append({'role': 'user', 'content': user})
    return msgs


def _sample(max_tokens, temperature):
    """Sampling params tuned for coherent, non-repetitive, on-topic answers."""
    def _f(name, default):
        try:
            return float(os.environ.get(name, default))
        except (TypeError, ValueError):
            return float(default)

    sample = {
        'max_tokens': int(max_tokens or MAX_TOKENS),
        'top_p': min(1.0, max(0.0, _f('ZER_TOP_P', 0.85))),
        'top_k': int(_f('ZER_TOP_K', 40)),
        'repeat_penalty': _f('LLM_REPEAT_PENALTY', 1.08),
        'presence_penalty': _f('LLM_PRESENCE_PENALTY', 0.2),
        'frequency_penalty': _f('LLM_FREQUENCY_PENALTY', 0.3),
    }
    temp = _f('LLM_TEMPERATURE', temperature if temperature is not None else 0.7)
    sample['temperature'] = max(0.0, min(1.5, temp))
    return sample


def chat(system, user, history=None, model=None, max_tokens=MAX_TOKENS,
         timeout=None, lang=None):
    """One full reply from the language's engine; None when unavailable/failed."""
    key = _lang_key(lang)
    if not load(key):
        return None
    messages = _messages(system, user, history)
    with _gen_lock:
        try:
            result = _llms[key].create_chat_completion(
                messages=messages, **_sample(max_tokens, 0.7))
            reply = (result.get('choices') or [{}])[0]\
                .get('message', {}).get('content')
        except Exception:
            return None
    return (reply or '').strip() or None


def chat_stream(system, user, history=None, model=None, max_tokens=MAX_TOKENS,
                temperature=0.7, timeout=None, lang=None):
    """Generate a reply token-by-token. Yields text deltas; then ends."""
    key = _lang_key(lang)
    if not load(key):
        return
    messages = _messages(system, user, history)
    with _gen_lock:
        try:
            for chunk in _llms[key].create_chat_completion(
                    messages=messages, stream=True, **_sample(max_tokens, temperature)):
                delta = (chunk.get('choices') or [{}])[0].get('delta', {}) \
                    .get('content', '') or ''
                if delta:
                    yield delta
        except Exception:
            return


if __name__ == '__main__':
    t0 = time.time()
    ok = load('am')
    print(f'load(am) → {ok} in {time.time() - t0:.1f}s  ({status()})')
    if ok:
        print(chat('አንተ ዘር ነህ።', 'ሰላም!', max_tokens=40, lang='am'))
