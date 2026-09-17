"""Free keyless machine-translation helpers (Amharic <-> English) with a
smart translation-quality layer.

Pipeline
--------
1. A user-edited / verified translation is looked up first — stored corrections
   always win (deterministic, human-checked).
2. Candidate translations are generated from MyMemory (full response incl. its
   translation-memory match %), Google's public endpoint, and an offline
   Amharic<->English glossary for simple word/phrase lookups.
3. Every candidate is *scored* for the best choice: glossary fidelity, a
   back-translation agreement check (translate it back and compare to the
   original), length sanity, machine-translation match bonus, echo/markup
   penalties, and a bonus for translations that match stored user corrections.
4. The best-scoring translation wins and is cached.

The user can verify or correct any translation through the web UI; verified
and corrected pairs are persisted to data/user_translations.json and make
later translations faster and better.

No API keys required. Pure stdlib.
"""

import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request

from amharic_nlp.letters import family_order, letter_of

USER_AGENT = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) HisarBot/1.0'}

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
# User-generated data (corrections) lives in a writable dir so a Fly volume can
# persist it; read-only learned artifacts stay in DATA_DIR.
USER_DATA_DIR = os.environ.get('HISAR_USERDATA_DIR') or DATA_DIR
CORRECTIONS_PATH = os.path.join(USER_DATA_DIR, 'user_translations.json')

_CACHE = {}
_CACHE_LOCK = threading.Lock()

LANG_ALIAS = {
    'amharic': 'am', 'amh': 'am', 'am': 'am',
    'english': 'en', 'eng': 'en', 'en': 'en',
}

# ---------------------------------------------------------------------------
# small curated Amharic <-> English glossary.
# Used (a) offline for simple word/phrase translation and (b) to give the
# translation-quality scorer a fidelity signal ("did the translation keep the
# meaning of these words?").
# ---------------------------------------------------------------------------
_LEX = {
    'ሰላም': ('hello', 'peace', 'hi'),
    'አመሰግናለሁ': ('thank', 'thanks'),
    'እባክህ': ('please',),
    'ውሃ': ('water',),
    'እሳት': ('fire',),
    'ቤት': ('house', 'home'),
    'ሰው': ('person', 'man', 'human', 'people'),
    'ሴት': ('woman', 'female', 'lady'),
    'ወንድ': ('man', 'male'),
    'ልጅ': ('child', 'son', 'daughter', 'kid'),
    'ብር': ('birr', 'money', 'silver'),
    'ወርቅ': ('gold',),
    'ብረት': ('iron',),
    'እንጀራ': ('injera', 'bread'),
    'ዳቦ': ('bread',),
    'ቡና': ('coffee',),
    'ሻይ': ('tea',),
    'እንቁላል': ('egg',),
    'ወተት': ('milk',),
    'ሥጋ': ('meat',),
    'ዓሣ': ('fish',),
    'ስኳር': ('sugar',),
    'ጨው': ('salt',),
    'እህል': ('grain', 'cereal'),
    'ነጭ': ('white',),
    'ጥቁር': ('black',),
    'ቀይ': ('red',),
    'ሰማያዊ': ('blue',),
    'አረንጓዴ': ('green',),
    'ትልቅ': ('big', 'large', 'great'),
    'ትንሽ': ('small', 'little'),
    'ጥሩ': ('good', 'nice', 'fine'),
    'መጥፎ': ('bad', 'evil'),
    'አዲስ': ('new',),
    'አሮጌ': ('old',),
    'ውብ': ('beautiful', 'pretty'),
    'ፈጣን': ('fast', 'quick'),
    'ቀስ': ('slow',),
    'ፀሐይ': ('sun',),
    'ጨረቃ': ('moon',),
    'ኮከብ': ('star',),
    'ሰማይ': ('sky', 'heaven'),
    'ምድር': ('earth', 'land', 'ground'),
    'ባሕር': ('sea', 'ocean'),
    'ተራራ': ('mountain',),
    'ወንዝ': ('river',),
    'ዛፍ': ('tree',),
    'አበባ': ('flower',),
    'በረዶ': ('snow', 'ice'),
    'ዝናብ': ('rain',),
    'ድሪጋ': ('storm',),
    'መጽሐፍ': ('book',),
    'ሱቅ': ('shop', 'store'),
    'ትምህርት': ('education', 'learning', 'study', 'school'),
    'ትምህርት ቤት': ('school',),
    'አስተማሪ': ('teacher',),
    'ተማሪ': ('student',),
    'ሐኪም': ('doctor',),
    'ሀኪም': ('doctor',),
    'እናት': ('mother', 'mom'),
    'አባት': ('father', 'dad'),
    'ወንድም': ('brother',),
    'እህት': ('sister',),
    'ጓደኛ': ('friend',),
    'ማን': ('who',),
    'ምን': ('what',),
    'ለምን': ('why',),
    'የት': ('where',),
    'መቼ': ('when',),
    'እንዴት': ('how',),
    'አዎ': ('yes',),
    'አይደለም': ('no',),
    'አንተ': ('you',),
    'እሱ': ('he', 'him', 'it'),
    'እሷ': ('she', 'her'),
    'እኔ': ('i', 'me'),
    'እኛ': ('we', 'us'),
    'እናንተ': ('you',),
    'እነሱ': ('they', 'them'),
    'አንድ': ('one', 'a'),
    'ሁለት': ('two',),
    'ሦስት': ('three',),
    'አራት': ('four',),
    'አምስት': ('five',),
    'ስድስት': ('six',),
    'ሰባት': ('seven',),
    'ስምንት': ('eight',),
    'ዘጠኝ': ('nine',),
    'አሥር': ('ten',),
    'መሄድ': ('go', 'went'),
    'መምጣት': ('come', 'came'),
    'መብላት': ('eat', 'ate'),
    'መጠጣት': ('drink',),
    'መስማት': ('hear', 'listen'),
    'ማየት': ('see', 'look', 'watch'),
    'ማውራት': ('speak', 'talk', 'say'),
    'ማድረግ': ('do', 'make'),
    'መስጠት': ('give',),
    'መውሰድ': ('take',),
    'መፈለግ': ('find', 'search', 'look for'),
    'መሆን': ('be', 'become'),
    'መውደድ': ('love', 'like'),
    'መጠየቅ': ('ask', 'question'),
}

# reverse lookup: english word (lower) -> one amharic gloss (for en→am scoring)
_REV_LEX = {}
for _am, _ens in _LEX.items():
    for _en in _ens:
        _REV_LEX.setdefault(_en, _am)


def _canon(lang):
    return LANG_ALIAS.get(str(lang).strip().lower(), str(lang).strip().lower())


def _first(text, charset):
    return ''.join(c for c in text if c in charset).strip()


def _clean_split(parts):
    return ''.join(parts or []).replace(' \n', ' ').strip()


def _collapse(text):
    return ' '.join((text or '').split())


# ---------------------------------------------------------------------------
# correction / verification store
# ---------------------------------------------------------------------------
_CORR = []                  # list of records
_CORR_BY_KEY = {}           # (src, dst, collapsed_text) -> record
_CORR_LOCK = threading.Lock()
_CORR_LOADED = False
_CORR_REV = 0               # bumped whenever the correction set changes

# review UI cache: (am,en,status) rows built from glossary + corrections + words
_PAIRS = None
_PAIRS_REV = -1
_PAIRS_LOCK = threading.Lock()
_STOPWORDS_PATH = os.path.join(DATA_DIR, 'stopwords.txt')
_WORDS_PATH = os.path.join(DATA_DIR, 'amharic_words.json')
_REVIEW_WORD_LIMIT = 1200   # frequent non-stop words offered for translation
# Only translations below this confidence are queued for human checking.
CONFIDENCE_THRESHOLD = 0.90


def _corr_key(src, dst, text):
    return (src, dst, _collapse(text))


def _load_corrections():
    global _CORR, _CORR_BY_KEY, _CORR_LOADED, _CORR_REV
    with _CORR_LOCK:
        if _CORR_LOADED:
            return
        _CORR = []
        _CORR_BY_KEY = {}
        _CORR_REV += 1
        try:
            with open(CORRECTIONS_PATH, encoding='utf-8') as f:
                data = json.load(f)
            for rec in data.get('translations', []) or []:
                if not isinstance(rec, dict) or 'text' not in rec:
                    continue
                key = _corr_key(rec.get('src', 'am'), rec.get('dst', 'en'),
                                rec.get('text', ''))
                _CORR.append(rec)
                _CORR_BY_KEY[key] = rec
        except (OSError, ValueError):
            pass
        _CORR_LOADED = True


def _save_corrections():
    try:
        os.makedirs(os.path.dirname(CORRECTIONS_PATH) or '.', exist_ok=True)
        tmp = CORRECTIONS_PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'translations': _CORR,
                       'updated': time.strftime('%Y-%m-%d %H:%M:%S')},
                      f, ensure_ascii=False, indent=2)
        os.replace(tmp, CORRECTIONS_PATH)
    except OSError:
        pass


def _corrections_lookup(src, dst, text):
    _load_corrections()
    with _CORR_LOCK:
        rec = _CORR_BY_KEY.get(_corr_key(src, dst, text))
        if rec:
            rec['used'] = rec.get('used', 0) + 1
        return rec


def store_verification(text, src, dst, translation, correction='', engine='user', by='anonymous'):
    """Persist a user verification (ok) or a corrected translation.

    Returns the stored record. Existing records for the same (src, dst, text)
    are updated in place; exact engine output that already matches a stored
    correction bumps the 'endorsed' counter.
    """
    global _CORR_REV
    text = _collapse(text)
    translation = _collapse(translation)
    correction = _collapse(correction) or translation
    if not text or not correction:
        return None
    _load_corrections()
    with _CORR_LOCK:
        key = _corr_key(src, dst, text)
        rec = _CORR_BY_KEY.get(key)
        if rec is None:
            rec = {
                'id': 'u%d' % (len(_CORR) + 1),
                'src': src, 'dst': dst, 'text': text,
                'original': translation, 'corrected': correction,
                'engine': engine, 'verified_by': by,
                'endorsed': 0, 'used': 0,
                'created_ts': time.strftime('%Y-%m-%d %H:%M:%S'),
            }
            _CORR.append(rec)
            _CORR_BY_KEY[key] = rec
        else:
            rec['corrected'] = correction
            rec['original'] = translation
            rec['engine'] = engine
            if _collapse(translation) == _collapse(rec['corrected']):
                rec['endorsed'] = rec.get('endorsed', 0) + 1
        _save_corrections()
        _CORR_REV += 1
        return rec


def corrections_review(limit=100):
    _load_corrections()
    with _CORR_LOCK:
        items = sorted(_CORR, key=lambda r: r.get('created_ts', ''), reverse=True)
        return [dict(r) for r in items[:limit]]


def corrections_count():
    _load_corrections()
    with _CORR_LOCK:
        return len(_CORR)


# ---------------------------------------------------------------------------
# word/translation review catalogue (powers the /review UI)
# ---------------------------------------------------------------------------
def _load_stopwords():
    try:
        with open(_STOPWORDS_PATH, encoding='utf-8') as f:
            return {ln.strip() for ln in f
                    if ln.strip() and not ln.lstrip().startswith('#')}
    except OSError:
        return set()


def _frequent_words(limit=_REVIEW_WORD_LIMIT):
    """Frequent content words from the spelling dictionary that have no gloss
    yet — offered to users so they can add a correct English translation."""
    try:
        with open(_WORDS_PATH, encoding='utf-8') as f:
            data = json.load(f)
        entries = data.get('words', [])
    except (OSError, ValueError):
        return []
    stop = _load_stopwords()
    out = []
    for e in entries:
        w = (e.get('w') or '').strip()
        if len(w) < 3 or w in stop or w in _LEX:
            continue
        out.append(w)
        if len(out) >= limit:
            break
    return out


def _pair_status(rec, suggested):
    """Map a correction record (or absence) to a review status."""
    if rec is not None:
        original = _collapse(rec.get('original') or '')
        corrected = _collapse(rec.get('corrected') or '')
        if corrected and corrected == original:
            return 'verified'
        return 'corrected'
    return 'suggested' if suggested else 'untranslated'


def _pair_confidence(rec, suggested, am, en, glosses=()):
    """Heuristic 0..1 confidence that a word's English translation is correct.

    * human-verified / corrected pairs score on endorsements (>= 0.90),
    * curated single-glossary entries sit at 0.92 (trusted, hidden from review),
    * ambiguous multi-glossary words fall below the 0.90 review threshold,
    * untranslated words score 0.0.
    """
    en = _collapse(en)
    if not en:
        return 0.0
    if rec is not None:
        original = _collapse(rec.get('original') or '')
        corrected = _collapse(rec.get('corrected') or '')
        endorsed = rec.get('endorsed', 0) or 0
        if corrected and corrected == original:
            return round(min(0.99, 0.90 + 0.02 * endorsed), 3)
        return 0.95
    if not suggested or _collapse(suggested) != en:
        return 0.4                       # an unsourced / odd suggestion
    conf = 0.92
    if len(glosses) > 1:
        conf -= 0.06                     # several valid readings → ambiguous
    am_words = max(1, len(am.split()))
    en_words = max(1, len(en.split()))
    ratio = en_words / am_words
    if ratio < 0.5 or ratio > 3.0:
        conf -= 0.1
    return round(max(0.05, min(0.99, conf)), 3)


def _build_pairs():
    """Build (once per correction revision) the catalogue the review UI shows."""
    global _PAIRS, _PAIRS_REV
    _load_corrections()
    with _CORR_LOCK:
        rev = _CORR_REV
        recs = [dict(r) for r in _CORR]

    pairs = []
    seen = set()
    rec_by_text = {}
    for r in recs:
        rec_by_text.setdefault(_collapse(r.get('text') or ''), r)

    for am, ens in _LEX.items():
        suggested = ens[0] if ens else ''
        rec = rec_by_text.get(am)
        en = _collapse((rec.get('corrected') or rec.get('original')) if rec else suggested)
        pairs.append({
            'am': am, 'en': en or suggested,
            'status': _pair_status(rec, suggested),
            'source': 'glossary' if not rec else 'user',
            'endorsed': rec.get('endorsed', 0) if rec else 0,
            'verified': rec is not None,
            'confidence': _pair_confidence(rec, suggested, am, en or suggested, ens),
            'letter': letter_of(am),
        })
        seen.add(am)

    for r in recs:
        am = _collapse(r.get('text') or '')
        if not am or am in seen:
            continue
        em = _collapse(r.get('corrected') or r.get('original') or '')
        pairs.append({
            'am': am, 'en': em,
            'status': _pair_status(r, em),
            'source': 'user',
            'endorsed': r.get('endorsed', 0),
            'verified': True,
            'confidence': _pair_confidence(r, '', am, em),
            'letter': letter_of(am),
        })
        seen.add(am)

    for w in _frequent_words():
        if w in seen:
            continue
        pairs.append({'am': w, 'en': '', 'status': 'untranslated',
                      'source': 'dictionary', 'endorsed': 0, 'verified': False,
                      'confidence': 0.0, 'letter': letter_of(w)})
        seen.add(w)

    with _PAIRS_LOCK:
        _PAIRS = pairs
        _PAIRS_REV = rev
    return pairs


def _ensure_pairs():
    _load_corrections()
    with _CORR_LOCK:
        current = _CORR_REV
    if _PAIRS is None or _PAIRS_REV != current:
        return _build_pairs()
    return _PAIRS


def translation_letters():
    """Letter (fidel family) breakdown of the review catalogue, in fidel order."""
    items = _ensure_pairs()
    counts = {}
    for p in items:
        key = p.get('letter') or 'ሌላ'
        counts[key] = counts.get(key, 0) + 1
    ordered = [lt for lt in family_order() if lt in counts]
    ordered += [lt for lt in sorted(k for k in counts if k not in family_order())]
    return {
        'total': len(items),
        'letters': [{'letter': lt, 'count': counts[lt]} for lt in ordered],
    }


def list_translations(query='', status='all', limit=100, offset=0,
                      max_confidence=None, letter=None):
    """Paginated catalogue for the review UI.

    status ∈ {'all', 'review', 'verified', 'corrected', 'untranslated'}.
    'review' shows only translations scored below CONFIDENCE_THRESHOLD (90%);
    pass ``max_confidence`` to override the threshold for any status.
    """
    items = _ensure_pairs()
    if status in ('verified', 'corrected'):
        items = [p for p in items if p['status'] in ('verified', 'corrected')]
    elif status == 'untranslated':
        items = [p for p in items if p['status'] == 'untranslated']

    # 'review' = everything the scorer is less than 90% sure about.
    threshold = None
    if status == 'review':
        threshold = CONFIDENCE_THRESHOLD
    if max_confidence is not None:
        try:
            threshold = float(max_confidence)
        except (TypeError, ValueError):
            pass
    if threshold is not None:
        items = [p for p in items if p['confidence'] < threshold]
        if status == 'review':
            # most uncertain first — the words that most need a human
            items = sorted(items, key=lambda p: p.get('confidence', 0.0))

    if letter:
        items = [p for p in items if (p.get('letter') or 'ሌላ') == letter]
    q = _collapse(query)
    if q:
        ql = q.lower()
        items = [p for p in items if q in p['am'] or ql in (p['en'] or '').lower()]
    total = len(items)
    try:
        offset = max(0, int(offset))
        limit = max(1, min(int(limit), 500))
    except (TypeError, ValueError):
        offset, limit = 0, 100
    return {
        'total': total, 'offset': offset, 'limit': limit,
        'threshold': (threshold if threshold is not None else CONFIDENCE_THRESHOLD),
        'items': [dict(p) for p in items[offset:offset + limit]],
    }


def translation_stats():
    items = _ensure_pairs()
    stats = {'total': len(items), 'verified': 0, 'corrected': 0,
             'review': 0, 'untranslated': 0, 'glossary': len(_LEX),
             'threshold': CONFIDENCE_THRESHOLD, 'low_confidence': 0,
             'high_confidence': 0}
    for p in items:
        st = p['status']
        if st == 'verified':
            stats['verified'] += 1
        elif st == 'corrected':
            stats['corrected'] += 1
        elif st == 'suggested':
            stats['review'] += 1
        elif st == 'untranslated':
            stats['untranslated'] += 1
        if p.get('confidence', 0.0) < CONFIDENCE_THRESHOLD:
            stats['low_confidence'] += 1
        else:
            stats['high_confidence'] += 1
    return stats


# ---------------------------------------------------------------------------
# candidate engines
# ---------------------------------------------------------------------------
def _google(text, sl, tl):
    url = 'https://translate.googleapis.com/translate_a/single?' + urllib.parse.urlencode(
        {'client': 'gtx', 'sl': sl, 'tl': tl, 'dt': 't', 'q': text})
    with urllib.request.urlopen(urllib.request.Request(url, headers=USER_AGENT), timeout=12) as r:
        data = json.loads(r.read().decode('utf-8'))
    return _clean_split([seg[0] for seg in data[0] if seg and seg[0]])


def _google_candidates(text, sl, tl):
    val = _google(text, sl, tl)
    return [(val, 0.0, 'google')] if val else []


def _mymemory(text, sl, tl):
    url = 'https://api.mymemory.translated.net/get?' + urllib.parse.urlencode(
        {'q': text, 'langpair': '%s|%s' % (sl, tl), 'mt': '1'})
    with urllib.request.urlopen(urllib.request.Request(url, headers=USER_AGENT), timeout=12) as r:
        data = json.loads(r.read().decode('utf-8'))
    if data.get('responseStatus') != 200:
        raise RuntimeError('mymemory status %s' % data.get('responseStatus'))
    return (data.get('responseData') or {}).get('translatedText') or ''


def _mymemory_candidates(text, sl, tl):
    url = 'https://api.mymemory.translated.net/get?' + urllib.parse.urlencode(
        {'q': text, 'langpair': '%s|%s' % (sl, tl), 'mt': '1'})
    with urllib.request.urlopen(urllib.request.Request(url, headers=USER_AGENT), timeout=12) as r:
        data = json.loads(r.read().decode('utf-8'))
    out = []
    best = (data.get('responseData') or {}).get('translatedText') or ''
    if best:
        out.append((best, 0.0, 'mymemory'))
    for m in data.get('matches', []) or []:
        tr = (m.get('translation') or '').strip()
        if not tr:
            continue
        try:
            mm = float(str(m.get('match', '0')).rstrip('%')) / 100.0
        except (TypeError, ValueError):
            mm = 0.0
        out.append((tr, mm, 'mymemory'))
    return out


def _lex_translate(text, src, dst):
    """Offline glossary translation: gloss known words, keep the rest as-is."""
    if src == 'am' and dst == 'en':
        lookup = _LEX
    elif src == 'en' and dst == 'am':
        lookup = _REV_LEX
    else:
        return ''
    words = (text or '').split()
    out = []
    for w in words:
        gloss = lookup.get(w) or lookup.get(w.lower())
        if gloss:
            out.append(gloss[0])
        else:
            out.append(w)
    glue = ' ' if dst == 'en' else ' '
    return glue.join(out) if out else ''


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------
def _dice(a, b):
    """Dice coefficient on word sets — how much does back-translation overlap
    the original text? 1.0 = identical meaning signal, 0.0 = unrelated."""
    ta = set(re.findall(r'\S+', (a or '').lower()))
    tb = set(re.findall(r'\S+', (b or '').lower()))
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return round(2.0 * inter / (len(ta) + len(tb)), 3)


def _score(text, cand, src, dst, tm=0.0, dice=None, nxtra=0.0):
    """Heuristic translation-quality score. Higher is better."""
    score = nxtra
    reasons = []
    src_text = _collapse(text)
    c = _collapse(cand)
    if not c:
        return -10.0, ['empty']
    if c.lower() == src_text.lower() and _first(src_text, 'ሀሐአዐ') != '':
        score -= 1.5
        reasons.append('echo')
    low = c.lower()
    if 'http' in low or ('<' in low and '>' in low):
        score -= 2.0
        reasons.append('markup')
    if re.search(r'&[a-z]+;', low):
        score -= 0.5
        reasons.append('html-entities')

    a_tokens = len(src_text.split())
    b_tokens = len(c.split())
    if a_tokens:
        ratio = b_tokens / a_tokens
        if not (0.2 <= ratio <= 6.0):
            score -= 0.8
            reasons.append('length-ratio')

    # glossary fidelity
    if dst == 'en':
        matched = known = 0
        for w in src_text.lower().split():
            gloss = _LEX.get(w)
            if gloss:
                known += 1
                if any(g in low for g in gloss):
                    matched += 1
                    score += 0.15
                else:
                    score -= 0.08
        if known:
            reasons.append('glossary %d/%d' % (matched, known))
    elif dst == 'am':
        matched = known = 0
        for w in src_text.lower().split():
            am = _REV_LEX.get(w)
            if am:
                known += 1
                if am in c:
                    matched += 1
                    score += 0.15
                else:
                    score -= 0.08
        if known:
            reasons.append('glossary %d/%d' % (matched, known))

    if tm:
        score += min(max(tm, 0.0), 1.0) * 0.2
        reasons.append('tm %.0f%%' % (tm * 100))

    if dice is not None:
        score += 0.5 * dice
        reasons.append('back-translation %.2f' % dice)
    return round(score, 3), reasons


def _word_evidence(text, candidate, src, dst):
    """Return lightweight, explainable glossary evidence for a translation."""
    source_words = _collapse(text).split()
    target = _collapse(candidate).lower()
    lookup = _LEX if src == 'am' and dst == 'en' else _REV_LEX
    evidence = []
    for word in source_words:
        clean = word.strip('.,!?;:።፣፤፥፦፧፨()[]{}"\'')
        glosses = lookup.get(clean) or lookup.get(clean.lower())
        if not glosses:
            continue
        glosses = (glosses,) if isinstance(glosses, str) else glosses
        matched = next((g for g in glosses if g.lower() in target), None)
        evidence.append({
            'source': clean,
            'expected': list(glosses[:3]),
            'matched': matched,
            'verified': bool(matched),
        })
    return evidence


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def best_translate(text, src='am', dst='en', online=True):
    """Translate with the smart quality layer.

    Returns a dict: {translated, score, engine, verified, correction_id?,
    reasons}. Stored user corrections take priority; otherwise the best-scoring
    candidate (glossary fidelity + back-translation agreement + sanity checks)
    is returned.
    """
    text = _collapse(text)
    if not text:
        return {'translated': '', 'score': 0.0, 'engine': 'none',
                'verified': False, 'reasons': []}
    src = _canon(src)
    dst = _canon(dst)
    if src == dst:
        return {'translated': text, 'score': 1.0, 'engine': 'identity',
                'verified': False, 'reasons': ['same-language']}

    key = (src, dst, text)

    # stored user corrections always win — checked before the cache so a new
    # correction takes effect immediately without a server restart
    rec = _corrections_lookup(src, dst, text)
    if rec and rec.get('corrected'):
        result = {
            'translated': rec['corrected'],
            'score': 1.0,
            'engine': 'correction',
            'verified': True,
            'correction_id': rec.get('id'),
            'reasons': ['stored user correction'],
        }
        with _CACHE_LOCK:
            _CACHE[key] = result
        return dict(result)

    with _CACHE_LOCK:
        if key in _CACHE:
            return dict(_CACHE[key])

    raw = []
    gloss = _lex_translate(text, src, dst)
    if gloss:
        raw.append((gloss, 0.0, 'lexicon'))
    if online:
        for gen in (_mymemory_candidates, _google_candidates):
            try:
                raw.extend(gen(text, src, dst))
            except Exception:
                pass

    seen = set()
    cands = []
    for cand, tm, eng in raw:
        norm = _collapse(cand).lower()
        if not norm or norm in seen or norm == text.lower():
            continue
        seen.add(norm)
        cands.append({'text': _collapse(cand), 'tm': tm, 'eng': eng})

    if not cands:
        result = {'translated': '', 'score': 0.0, 'engine': 'none',
                  'verified': False, 'reasons': ['no candidates']}
        with _CACHE_LOCK:
            _CACHE[key] = result
        return dict(result)

    # preliminary scores (sanity + glossary), then back-translate top two
    for c in cands:
        c['pre'], c['reasons'] = _score(text, c['text'], src, dst, tm=c['tm'])
    cands.sort(key=lambda c: c['pre'], reverse=True)

    for i, c in enumerate(cands):
        dice = None
        if i < 2 and online and c['eng'] != 'lexicon':
            try:
                back = _google(c['text'], dst, src)
                if back:
                    dice = _dice(back, text)
            except Exception:
                pass
        c['dice'] = dice
        c['score'], c['reasons'] = _score(text, c['text'], src, dst,
                                          tm=c['tm'], dice=dice)

    best = max(cands, key=lambda c: c['score'])
    evidence = _word_evidence(text, best['text'], src, dst)
    result = {
        'translated': best['text'],
        'score': round(min(best['score'], 2.0), 3),
        'engine': best['eng'],
        'verified': False,
        'reasons': best['reasons'][:5],
        'word_evidence': evidence,
    }
    with _CACHE_LOCK:
        _CACHE[key] = result
    return dict(result)


def translate(text, src='am', dst='en', online=True):
    """Backwards-compatible shortcut: just the best translation string."""
    return best_translate(text, src, dst, online).get('translated', '')


if __name__ == '__main__':
    print('am→en:', translate('ሰላም! ስለ ኢትዮጵያ ቡና ንገረኝ', 'am', 'en'))
    print('am→en (offline):', translate('ሰላም ሰው ውሃ', 'am', 'en', online=False))
    print('en→am:', translate('Hello! Tell me about Ethiopian coffee.', 'en', 'am'))
    print('score sample:', best_translate('ሰላም ውሃ ቡና', 'am', 'en', online=False))
