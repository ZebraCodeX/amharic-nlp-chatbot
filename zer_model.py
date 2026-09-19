#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zer_model.py — the embedded Zer model framework.

Packs the fine-tuned Zer brain (Qwen2.5-1.5B, QLoRA-then-merged, GGUF Q4_K_M)
into the application as a first-class component, so the deployed app is
self-contained: it loads and runs the model itself through llama.cpp — no
external GPU host, no network round-trip, no API key.

    ZER_MODEL=path/to/zer-qwen-q4_k_m.gguf   python3 chat_app.py

The model file defaults to ``models/zer-qwen-q4_k_m.gguf`` next to this file.
Tuning knobs (env):

    ZER_MODEL     path to the .gguf file (default: ./models/zer-qwen-q4_k_m.gguf)
    ZER_THREADS   CPU threads for inference (default: min(8, cpu_count))
    ZER_CTX       context length in tokens  (default: 1024)
    ZER_BATCH     prompt batch tokens       (default: 512 — faster prefill)
    ZER_MAX_TOKENS default reply cap        (default: 512)

The engine is lazy: the first import starts a background warm-up so a request
never pays the full model load; ``load()`` blocks until ready (or returns False
if llama-cpp-python or the model file is missing — the app then falls back).

Usage:

    import zer_model
    zer_model.load()                       # warm-up (blocks until ready)
    zer_model.available()                  # is an inference engine reachable?
    zer_model.chat(system, user, history)  # one full reply
    for delta in zer_model.chat_stream(...):  # …or token-by-token (SSE)

Thread-safety: generation is serialized with a lock (llama.cpp context objects
are not safe for concurrent sampling), so concurrent Django/gunicorn threads
queue cleanly instead of corrupting state.
"""

import os
import threading
import time

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL_FILE = os.environ.get('ZER_MODEL') or os.path.join(
    REPO_ROOT, 'models', 'zer-qwen-q4_k_m.gguf')

MODEL_NAME = 'zer-embedded'
MAX_TOKENS = int(os.environ.get('ZER_MAX_TOKENS', '512'))

_llm = None
_state = 'idle'          # idle | loading | ready | error
_error = None
_load_lock = threading.RLock()
_gen_lock = threading.Lock()

# llama.cpp ack — cached so `available()` stays cheap at probe time.
_llama_cls = None
_llama_cls_lock = threading.Lock()


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


_error_msgs = []


def _config():
    n_threads = int(os.environ.get('ZER_THREADS', '0'))
    if n_threads <= 0:
        n_threads = min(8, os.cpu_count() or 4)
    return {
        'n_ctx': max(256, int(os.environ.get('ZER_CTX', '1024'))),
        'n_batch': max(32, int(os.environ.get('ZER_BATCH', '512'))),
        'n_threads': n_threads,
    }


def model_file():
    """Absolute path of the GGUF file this instance would load."""
    return MODEL_FILE


def file_available():
    return bool(MODEL_FILE) and os.path.exists(MODEL_FILE)


def load(wait=True):
    """Load the model into memory. Thread-safe; idempotent.

    Returns True once ready. Returns False quickly when llama-cpp-python is
    missing or the GGUF file is absent (the app keeps working offline).
    """
    global _llm, _state, _error
    with _load_lock:
        if _llm is not None:
            return True
        if not file_available():
            _state, _error = 'error', 'model file not found: %s' % MODEL_FILE
            return False
        Llama = _llama()
        if not Llama:
            _state, _error = 'error', _error_msgs[-1] if _error_msgs else 'llama_cpp missing'
            return False
        _state = 'loading'
        cfg = _config()
        t0 = time.time()
        try:
            _llm = Llama(
                model_path=MODEL_FILE,
                n_ctx=cfg['n_ctx'],
                n_batch=cfg['n_batch'],
                n_threads=cfg['n_threads'],
                verbose=False,
                use_mmap=True,
            )
            _state = 'ready'
        except Exception as exc:  # pragma: no cover - model/env dependent
            _llm = None
            _state = 'error'
            _error = str(exc).replace('\n', ' ')
            return False
        return True


def warm():
    """Start an eager background warm-up (non-blocking)."""
    thread = threading.Thread(target=load, name='zer-model-warm', daemon=True)
    thread.start()
    return thread


def available():
    """True when a functional inference engine will be available (fast check)."""
    with _load_lock:
        if _llm is not None:
            return True
    if not file_available():
        return False
    return bool(_llama())


def status():
    """Stable status dict for /api/llm-status and the help page."""
    return {
        'available': available(),
        'backend': 'embedded',
        'model': os.path.basename(MODEL_FILE) if file_available() else None,
        'state': _state,
        'loaded': _llm is not None,
        'file': MODEL_FILE if file_available() else None,
        'error': _error,
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
    sample = {'max_tokens': int(max_tokens or MAX_TOKENS),
              'top_p': 0.9, 'repeat_penalty': 1.1}
    try:
        sample['temperature'] = float(os.environ.get('LLM_TEMPERATURE', temperature or 0.7))
    except (TypeError, ValueError):
        sample['temperature'] = temperature or 0.7
    if sample['temperature'] <= 0:
        sample['do_sample'] = False
    return sample


def chat(system, user, history=None, model=None, max_tokens=MAX_TOKENS,
         timeout=None):
    """One full reply from the embedded model; None when unavailable/failed."""
    if not load():
        return None
    messages = _messages(system, user, history)
    with _gen_lock:
        try:
            result = _llm.create_chat_completion(
                messages=messages,
                temperature=float(os.environ.get('LLM_TEMPERATURE', '0.7')),
                **{k: v for k, v in _sample(max_tokens, 0.7).items()
                   if k not in ('temperature',)})
            reply = (result.get('choices') or [{}])[0]\
                .get('message', {}).get('content')
        except Exception:
            return None
    return (reply or '').strip() or None


def chat_stream(system, user, history=None, model=None, max_tokens=MAX_TOKENS,
                temperature=0.7):
    """Generate a reply token-by-token. Yields text deltas; then ends."""
    if not load():
        return
    messages = _messages(system, user, history)
    with _gen_lock:
        try:
            for chunk in _llm.create_chat_completion(messages=messages,
                                                     stream=True, **_sample(max_tokens, temperature)):
                delta = (chunk.get('choices') or [{}])[0].get('delta', {}) \
                    .get('content', '') or ''
                if delta:
                    yield delta
        except Exception:
            return


if __name__ == '__main__':
    t0 = time.time()
    ok = load()
    print(f'load → {ok} in {time.time() - t0:.1f}s  ({status()})')
    if ok:
        print(chat('አንተ ዘር ነህ።', 'ሰላም!', max_tokens=40))