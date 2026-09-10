"""Free keyless machine-translation helpers (Amharic <-> English).

Uses the MyMemory free translation API as the primary engine and Google's
public translate endpoint as a fallback. No API keys required.

If an offline machine is ever desired, call translate() with
online=False and only the local cache will be consulted.
"""

import json
import threading
import time
import urllib.parse
import urllib.request

USER_AGENT = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) HisarBot/1.0'}
_CACHE = {}
_CACHE_LOCK = threading.Lock()

LANG_ALIAS = {
    'amharic': 'am', 'amh': 'am', 'am': 'am',
    'english': 'en', 'eng': 'en', 'en': 'en',
}


def _canon(lang):
    return LANG_ALIAS.get(str(lang).strip().lower(), str(lang).strip().lower())


def _first(text, charset):
    return ''.join(c for c in text if c in charset).strip()


def _clean_split(parts):
    text = ''.join(parts or [])
    return text.replace(' \n', ' ').strip()


def _google(text, sl, tl):
    url = 'https://translate.googleapis.com/translate_a/single?' + urllib.parse.urlencode(
        {'client': 'gtx', 'sl': sl, 'tl': tl, 'dt': 't', 'q': text})
    with urllib.request.urlopen(urllib.request.Request(url, headers=USER_AGENT), timeout=12) as r:
        data = json.loads(r.read().decode('utf-8'))
    return _clean_split([seg[0] for seg in data[0] if seg and seg[0]])


def _mymemory(text, sl, tl):
    url = 'https://api.mymemory.translated.net/get?' + urllib.parse.urlencode(
        {'q': text, 'langpair': '%s|%s' % (sl, tl), 'mt': '1'})
    with urllib.request.urlopen(urllib.request.Request(url, headers=USER_AGENT), timeout=12) as r:
        data = json.loads(r.read().decode('utf-8'))
    if data.get('responseStatus') != 200:
        raise RuntimeError('mymemory status %s' % data.get('responseStatus'))
    return (data.get('responseData') or {}).get('translatedText') or ''


def translate(text, src='am', dst='en', online=True):
    """Translate text from src to dst (free, keyless).

    Returns the translated string, or '' on failure.
    """
    text = (text or '').strip()
    if not text:
        return ''
    src = _canon(src)
    dst = _canon(dst)
    if src == dst:
        return text

    key = (src, dst, text)
    with _CACHE_LOCK:
        if key in _CACHE:
            return _CACHE[key]

    engines = [_mymemory, _google]
    if not online:
        engines = []

    out = ''
    for engine in engines:
        try:
            out = engine(text, src, dst)
            if out:
                break
        except Exception:
            out = ''

    with _CACHE_LOCK:
        _CACHE[key] = out
    return out


if __name__ == '__main__':
    print('am→en:', translate('ሰላም! ስለ ኢትዮጵያ ቡና ንገረኝ', 'am', 'en'))
    print('en→am:', translate('Hello! Tell me about Ethiopian coffee.', 'en', 'am'))