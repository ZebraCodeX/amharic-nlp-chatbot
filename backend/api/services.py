"""Service layer: a thin, thread-safe wrapper around the stdlib NLP brain.

The Django/DRF layer never talks to `chatbot`/`translator` internals directly —
it goes through these functions, which keep singletons and locks in one place.
"""
import json
import os
import threading
import time

_lock = threading.RLock()
_assistant = None
_suggester = None
_words_cache = None
_ngram_cache = None
_words_lock = threading.Lock()


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------
def get_assistant():
    global _assistant
    with _lock:
        if _assistant is None:
            from chatbot import AmharicAssistant
            _assistant = AmharicAssistant()
        return _assistant


def get_zer():
    global _assistant
    with _lock:
        from zer import get_zer as _get_zer
        z = _get_zer()
        _assistant = z._am          # keep a handle for other helpers
        return z


def chat(text, history=None, lang=None):
    """One bilingual Zer turn, serialized so concurrent requests can't interleave."""
    from chatbot import normalize_history
    text = (text or '').strip()
    if not text:
        return {'reply': 'ምን ልርዳህ? / How can I help?',
                'source': 'empty', 'confidence': 1.0, 'lang': lang or 'unknown',
                'followups': []}
    z = get_zer()
    with _lock:
        norm = normalize_history(history) if isinstance(history, list) else []
        while norm and norm[-1].get('user') == text:
            norm.pop()
        z._am.history = norm[:10]
        en_history = []
        for turn in norm[:6]:
            if turn.get('user'):
                en_history.append({'role': 'user', 'content': turn['user']})
            if turn.get('reply'):
                en_history.append({'role': 'assistant', 'content': turn['reply']})
        start = time.time()
        result = z.respond(text, lang=lang, history=en_history, use_llm=True)
    result['elapsed_ms'] = round((time.time() - start) * 1000)
    return result


# ---------------------------------------------------------------------------
# type-ahead / dictionaries
# ---------------------------------------------------------------------------
def get_suggester():
    global _suggester
    with _lock:
        if _suggester is None:
            from amharic_nlp import Suggester
            _suggester = Suggester()
        return _suggester


def suggest(text, elapsed=True):
    start = time.time()
    with _lock:
        result = get_suggester().suggest(text)
    if elapsed:
        result['elapsed_ms'] = round((time.time() - start) * 1000)
    return result


def _data_path(name):
    from chatbot import DATA_DIR
    return os.path.join(DATA_DIR, name)


def words():
    global _words_cache
    with _words_lock:
        if _words_cache is None:
            try:
                with open(_data_path('amharic_words.json'), encoding='utf-8') as f:
                    _words_cache = json.load(f)
            except (OSError, ValueError):
                _words_cache = {'words': []}
        return _words_cache


def dictionary_letters():
    """The per-letter index of the Amharic dictionary (fidel order + counts)."""
    data = words()
    return {
        'count': data.get('count', 0),
        'letters': data.get('letters', []),
    }


def dictionary_by_letter(letter, limit=100, offset=0):
    """All dictionary words whose first fidel family is ``letter``."""
    data = words()
    by = data.get('by_letter') or {}
    items = by.get(letter, [])
    try:
        offset = max(0, int(offset))
        limit = max(1, min(int(limit), 1000))
    except (TypeError, ValueError):
        offset, limit = 0, 100
    return {
        'letter': letter,
        'total': len(items),
        'offset': offset,
        'limit': limit,
        'words': items[offset:offset + limit],
    }


def ngram():
    global _ngram_cache
    with _words_lock:
        if _ngram_cache is None:
            try:
                with open(_data_path('nl_model.json'), encoding='utf-8') as f:
                    _ngram_cache = json.load(f)
            except (OSError, ValueError):
                _ngram_cache = {'unigram': {}, 'bigram': {}, 'trigram': {},
                                'starters': {}}
        return _ngram_cache


# ---------------------------------------------------------------------------
# translation + review
# ---------------------------------------------------------------------------
def translate(text, src='am', dst='en'):
    from translator import best_translate
    start = time.time()
    result = best_translate(text or '', src, dst)
    result['src'] = src
    result['to'] = dst
    result['elapsed_ms'] = round((time.time() - start) * 1000)
    return result


def translations(**kwargs):
    from translator import list_translations
    return list_translations(**kwargs)


def translation_stats():
    from translator import translation_stats as _stats
    return _stats()


def translation_letters():
    from translator import translation_letters as _letters
    return _letters()


def learning_stats():
    from learning import stats
    return stats()


def verify_translation(text, src, dst, translation, correction='', engine='user'):
    from translator import store_verification
    text = (text or '').strip()
    translation = (translation or '').strip()
    correction = correction.strip() if isinstance(correction, str) else ''
    if not text or (not translation and not correction):
        raise ValueError('text and translation required')
    rec = store_verification(text, src, dst, translation or correction,
                             correction=correction, engine=engine or 'user')
    if rec is None:
        raise ValueError('could not save')
    return rec


def corrections_review(limit=100):
    from translator import corrections_review as _review
    return _review(limit)


def corrections_count():
    from translator import corrections_count as _count
    return _count()


# ---------------------------------------------------------------------------
# speech (open-source STT/TTS — optional, degrades to the browser)
# ---------------------------------------------------------------------------
def speech_status():
    import zer_speech
    return zer_speech.status()


def speech_voices():
    import zer_speech
    return zer_speech.voices()


def transcribe(data, filename='audio.webm', language=None):
    import zer_speech
    return zer_speech.transcribe_bytes(data, filename=filename, language=language)


def synthesize(text, lang='am', **params):
    import zer_speech
    return zer_speech.synthesize(text, lang, **params)


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
def llm_status():
    try:
        import llm
        backend = llm._configured_backend()
        if backend:
            return {'available': True, 'backend': 'configured', 'model': backend[2]}
        raw = llm._ollama_endpoint()
        if raw:
            return {'available': True, 'backend': 'ollama',
                    'model': (raw[3][0] if raw[3] else None)}
    except Exception:
        pass
    return {'available': False, 'backend': None, 'model': None}
