# -*- coding: utf-8 -*-
"""
english_brain.py — Zer's own English answers, with no model and no translation.

The runtime path must stay fast and fully self-contained, so everything here is
served from local data:

  * an English mirror of the knowledge base (`data/knowledge_base_en.json`),
    compiled ahead of time by `tools/build_english_kb.py`
  * the shared offline skills — code generation (`codegen.py`), the calendar
    (`et_calendar.py`) and the clock
  * a small English math parser

`zer.py` calls `respond()` for English turns instead of ever saying "connect a
language model".
"""

import json
import os
import random
import re
from datetime import datetime

from et_calendar import GREGORIAN_MONTHS, MONTHS, gregorian_to_ethiopic, weekday

from chatbot import DATA_DIR

_KB_EN_FILE = os.path.join(DATA_DIR, 'knowledge_base_en.json')

_WORD_RE = re.compile(r"[a-z0-9']+")
_ETHIOPIC_RE = re.compile(r'[\u1200-\u137f]+')

_kb = None
_index = None

# --- English number words → digits (for the math parser) ---------------------
_NUM_WORDS = {
    'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11,
    'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
    'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19,
    'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60,
    'seventy': 70, 'eighty': 80, 'ninety': 90, 'hundred': 100,
    'thousand': 1000,
}
_OP_WORDS = [
    (r'\b(plus|added to|add)\b', '+'),
    (r'\b(minus|subtract|less)\b', '-'),
    (r'\b(times|multiplied by|multiply by|multiply|into)\b', '*'),
    (r'\b(divided by|divide by|over)\b', '/'),
]

_MATH_RE = re.compile(r'(-?\d+)\s*([-+*/x])\s*(-?\d+)')
_TIME_RE = re.compile(r'\b(what|whats|what\'s)?\s*(time|clock)\b', re.I)
_DATE_RE = re.compile(r'\b(what|which|date|day|today|calendar)\b', re.I)
_MEAN_RE = re.compile(
    r'(?:what\s+does\s+([\u1200-\u137f]{2,20})\s+mean|'
    r'meaning\s+of\s+([\u1200-\u137f]{2,20})|'
    r'translate\s+([\u1200-\u137f]{2,20})|'
    r'([\u1200-\u137f]{2,20})\s+(?:means?|in\s+english|translation))', re.I)
_NAME_RE = re.compile(r'\bmy\s+name\s+is\s+([A-Za-z][A-Za-z\' -]{1,30})', re.I)
_REMEMBER_RE = re.compile(r'\b(remember|note|keep in mind)\b', re.I)


# ---------------------------------------------------------------------------
# knowledge base index
# ---------------------------------------------------------------------------
def _load():
    global _kb, _index
    if _kb is not None:
        return _kb
    try:
        with open(_KB_EN_FILE, encoding='utf-8') as f:
            _kb = json.load(f)
    except (OSError, ValueError):
        _kb = {'intents': [], 'dictionary': {}}
    _index = []
    for intent in _kb.get('intents', []):
        patterns = []
        for p in intent.get('patterns', []):
            p = (p or '').strip().lower()
            if not p:
                continue
            toks = _WORD_RE.findall(p)
            if toks:
                patterns.append((p, set(toks)))
        if patterns:
            _index.append((intent['tag'], patterns, intent.get('responses', [])))
    return _kb


def _match_intent(text):
    """Best (tag, responses, score) for an English query, or (None, …, 0)."""
    _load()
    low = text.lower()
    q = set(_WORD_RE.findall(low))
    if not q:
        return None, [], 0.0
    best = (None, [], 0.0)
    for tag, patterns, responses in _index:
        score = 0.0
        for phrase, toks in patterns:
            overlap = len(q & toks)
            if not overlap:
                continue
            s = overlap / (len(toks) ** 0.5 + 1.0)
            if ' ' in phrase and phrase in low:
                s += 1.0
            elif len(toks) <= 2 and overlap == len(toks) and len(q) <= 4:
                s += 0.4
            score = max(score, s)
        if score > best[2]:
            best = (tag, responses, score)
    return best


def _dictionary():
    return (_load().get('dictionary') or {})


# ---------------------------------------------------------------------------
# skills
# ---------------------------------------------------------------------------
def _math(text):
    t = ' ' + text.lower() + ' '
    for pat, sym in _OP_WORDS:
        t = re.sub(pat, ' %s ' % sym, t)
    t = t.replace('x', '*')
    for word, val in sorted(_NUM_WORDS.items(), key=lambda kv: -len(kv[0])):
        t = re.sub(r'\b%s\b' % word, str(val), t)
    m = _MATH_RE.search(t)
    if not m:
        return None
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    if op == '/' and b == 0:
        return "You can't divide by zero."
    result = {'+': a + b, '-': a - b, '*': a * b, '/': (a // b if a % b == 0 else round(a / b, 2))}[op]
    return f'The answer is {result}.'

def _time():
    now = datetime.now()
    eng = now.strftime('%I:%M %p').lstrip('0').lower()
    eth = (now.hour + 6) % 12 or 12
    return (f'It is {eng} ({now.strftime("%H:%M")}). '
            f'In the Ethiopian 12-hour clock that is {eth} o\'clock.')


def _date():
    now = datetime.now()
    ey, em, ed = gregorian_to_ethiopic(now.year, now.month, now.day)
    gmonth = GREGORIAN_MONTHS[now.month - 1]
    return (f"Today is {now.strftime('%A, %d %B %Y')}. "
            f"In the Ethiopian calendar it is {MONTHS[em - 1]} {ed}, {ey} "
            f"(ዓ.ም), {weekday(now.year, now.month, now.day)}.")


def _meaning(text):
    m = _MEAN_RE.search(text)
    if not m:
        return None
    word = next((g for g in m.groups() if g), None)
    if not word:
        return None
    gloss = _dictionary().get(word)
    if not gloss:
        # try a homophone/case-insensitive lookup
        for w, g in _dictionary().items():
            if w and (w in word or word in w):
                gloss = g
                break
    if not gloss:
        return None
    body = gloss[0] if isinstance(gloss, list) else gloss
    return f'«{word}» means: {body}'


def _code(text):
    try:
        import codegen
    except Exception:
        return None
    out = codegen.generate(text)
    if not out:
        return None
    # codegen writes an Amharic lead-in; keep the runnable code, restate it in English.
    block = re.search(r'```[^\n]*\n(.*?)```', out, re.S)
    if not block:
        return out
    fence = out.split('```')[1].split('\n', 1)[0] or 'python'
    return (f'Here is working {fence} code for that:\n\n```{fence}\n'
            f'{block.group(1).strip()}\n```')


def _remember(text, assistant):
    if assistant is None:
        return None
    m = _NAME_RE.search(text)
    if m:
        name = m.group(1).strip()
        assistant.user_name = name
        return f'Nice to meet you, {name}! I\'ll remember your name.'
    if _REMEMBER_RE.search(text):
        fact = _REMEMBER_RE.sub('', text, count=1).strip(' .,:;-')
        if len(fact) >= 2:
            assistant.memory[str(len(assistant.memory) + 1)] = fact
            save = getattr(assistant, '_save_memory', None)
            if callable(save):
                save()
            return f'Got it — I\'ll remember that: "{fact}".'
    return None


def _recall(text, assistant):
    if assistant is None:
        return None
    words = set(_WORD_RE.findall(text.lower()))
    if not words:
        return None
    for fact in getattr(assistant, 'memory', {}).values():
        fw = set(_WORD_RE.findall((fact or '').lower()))
        if fw and len(fw & words) / len(fw) >= 0.6:
            return f'You taught me: "{fact}".'
    return None


_FALLBACK = (
    "I can help with quite a lot, all offline: answer questions about "
    "technology, science, Ethiopia, AI, health and more; do math (try "
    "\"what is 12 times 8\"); explain Amharic words; write code; tell the time "
    "and the Ethiopian date; and hold a live voice conversation. "
    "Ask me something — or say it in Amharic too."
)


def respond(text, assistant=None, history=None):
    """Return an English reply dict, never None, never needing a model."""
    text = (text or '').strip()
    if not text:
        return _result('How can I help you?', 'empty')

    if _TIME_RE.search(text) and re.search(r'(what|time|now|is it)', text, re.I):
        return _result(_time(), 'en_rule')
    if re.search(r'\b(what|which)\b.*\b(date|day)\b', text, re.I) \
            or re.search(r'\btoday\b', text, re.I):
        return _result(_date(), 'en_rule')

    for skill in (_code, _meaning, _math):
        try:
            out = skill(text)
        except Exception:
            out = None
        if out:
            return _result(out, 'en_rule')

    # reasoning: word problems, comparisons, percentages, dates, known facts
    try:
        import reasoning
        answered = reasoning.solve(text, 'en')
    except Exception:
        answered = None
    if answered:
        return _result(answered, 'en_reason')

    remembered = _remember(text, assistant)
    if remembered:
        return _result(remembered, 'en_memory')

    recalled = _recall(text, assistant)
    if recalled:
        return _result(recalled, 'en_memory')

    tag, responses, score = _match_intent(text)
    if tag and responses and score >= 0.4:
        return _result(random.choice(responses), f'en_intent:{tag}', score)

    try:
        import reasoning
        honest = reasoning.unknown_reply(text, 'en')
    except Exception:
        honest = None
    if honest:
        return _result(honest, 'en_fallback')
    return _result(_FALLBACK, 'en_fallback')


def _result(reply, source, confidence=0.85):
    return {'reply': reply, 'source': source, 'confidence': confidence,
            'lang': 'en', 'followups': []}


def available():
    """True when the compiled English KB is present."""
    return os.path.exists(_KB_EN_FILE)
