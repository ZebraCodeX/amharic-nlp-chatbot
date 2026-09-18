# -*- coding: utf-8 -*-
"""
reasoning.py — Zer's fast, self-contained "thinking" layer.

The intent matcher alone can only *retrieve* canned answers, so a question like
«5 ወንድሞቼ አሉኝ 2ቱ ሄዱ ስንት ቀሩ?» used to be met with a topic essay. This module
computes instead of retrieving:

  * arithmetic word problems (Amharic + English number words)
  * comparisons / differences
  * averages and percentages
  * date arithmetic («ከ5 ቀን በኋላ …»)
  * direct lookups from the curated `data/facts.json`
  * an honest, non-generic reply when a numeric fact genuinely isn't known

Everything is pure stdlib and deterministic — no model, no network, sub-millisecond.
"""

import json
import os
import re
from datetime import date, datetime, timedelta

from et_calendar import GREGORIAN_MONTHS, MONTHS, gregorian_to_ethiopic, weekday

from chatbot import DATA_DIR

_FACTS_FILE = os.path.join(DATA_DIR, 'facts.json')

_DIGIT = re.compile(r'\d+(?:[.,]\d+)?')
_ETHIOPIC_WORD = re.compile(r'[\u1200-\u137f]+')
_WS_SPLIT = re.compile(r'[\s፤፥፣።!?፧«»…,;:()\[\]]+')

# operation cues (Amharic first, then English)
_CUES = {
    'sub': (r'ሄደ|ሄዱ|ቀረ|ቀሩ|ተቀነሰ|ተቀነሱ|ቀንስ|ቀነስ|ተጣራ|ተሸጠ|ተበላ|ሞተ|ሞቱ|'
            r'ጠፋ|ጠፉ|ለቀቀ|ለቀቁ|ተወ|ሰጠ|ተሰጠ|ላከ|አስወጣ|ተገደለ|'
            r'\bminus\b|\bless\b|\bleft\b|\bremain|\bate\b|\blost\b|\bgave\b|\bsubtract'),
    'add': (r'ጨመረ|ተጨመረ|ጨምር|ሲደመር|ሲጨመር|ደምረ|ጠቅላላ|በአጠቃላይ|ሁሉንም|'
            r'ድምር|አንድ ላይ|ሁሉም ሆኖ|ጨምሮ|'
            r'\bplus\b|\badd\b|\btotal\b|\bsum\b'),
    'mul': (r'ሲባዛ|ተባዛ|ተባዝቶ|እጥፍ|ዕጥፍ|እያንዳንዱ|በእያንዳንዱ|'
            r'\btimes\b|\bmultipl|\beach\b'),
    'div': (r'ሲከፈል|ተከፈለ|ተከፋፈለ|ተካፍለው|በእኩል|'
            r'\bdivided\b|\bshare\b|\beach\b|\bper\b'),
}
_CMP_BIG = r'ትልቁ|ትልቅ|ይበልጣል|የበለጠ|በላይ|greater|bigger|larger|\bmax\b|most'
_CMP_SMALL = r'ትንሹ|ትንሽ|ያንሳል|ያንሳ|ትንሽ|smaller|lesser|least|\bmin\b'
_DIFF = r'ልዩነት|ይለያያል|ልዩ|difference'
_AVG = r'አማካይ|አማካይነት|average|mean'
_PCT = r'በመቶ|%|percent'
_DATE_AFTER = r'በኋላ|በኃላ|ወዲያ|after|later|from now'
_DATE_BEFORE = r'በፊት|ቀደም|ትናንት|ago|before'
_FACT_Q = re.compile(
    r'ስንት|ምን\s*ያህል|ማን\s+ነው|የትኛው|እድሜ|ስፋት|ርዝመት|ከፍታ|'
    r'\bhow\s+(many|much|old|big|far|long|hot|tall|deep)\b|'
    r'\bwhat\s+is\s+the\b|\bwhats\s+the\b', re.I)

_facts = None


def _load_facts():
    global _facts
    if _facts is None:
        try:
            with open(_FACTS_FILE, encoding='utf-8') as f:
                _facts = json.load(f).get('facts', [])
        except (OSError, ValueError):
            _facts = []
    return _facts


def _numbers(text):
    """All numbers in the text with their positions (digits + Amharic words)."""
    found = []
    for m in _DIGIT.finditer(text):
        raw = m.group().replace(',', '')
        try:
            val = float(raw)
        except ValueError:
            continue
        found.append((val, m.start(), m.end()))
    try:
        from chatbot import AMH_NUM
    except Exception:
        AMH_NUM = {}
    # multi-word compounds first (they contain spaces)
    for key, val in sorted(AMH_NUM.items(), key=lambda kv: -len(kv[0])):
        if ' ' in key and key in text:
            pos = text.index(key)
            found.append((val, pos, pos + len(key)))
    # single tokens, tolerating a trailing suffix (ሁለቱ → ሁለት)
    for m in _ETHIOPIC_WORD.finditer(text):
        w = m.group()
        for cand in (w, w[:-1]):
            if cand in AMH_NUM:
                found.append((AMH_NUM[cand], m.start(), m.end()))
                break
    found.sort(key=lambda x: x[1])
    out, last_end = [], -1
    for val, start, end in found:
        if start >= last_end:
            out.append(val)
            last_end = end
    return out


def _fmt(n):
    if isinstance(n, float) and n.is_integer():
        n = int(n)
    if isinstance(n, float):
        return f'{n:g}'
    return str(n)


def _cue(text, name):
    return re.search(_CUES[name], text, re.I) is not None


# ---------------------------------------------------------------------------
# skills
# ---------------------------------------------------------------------------
def _date_math(text, lang):
    m = re.search(r'ከ?\s*([\u1200-\u137f0-9,]+)\s*(ቀን|ሳምንት|ሳምንታት|ወር|ዓመት|አመት)'
                  r'\s*(በኋላ|በኃላ|ወዲያ|በፊት|ቀደም)', text)
    if not m:
        return None
    nums = _numbers(m.group(1))
    if not nums:
        return None
    n = int(nums[0])
    unit = m.group(2)
    delta = {'ቀን': 1, 'ሳምንት': 7, 'ሳምንታት': 7, 'ወር': 30, 'ዓመት': 365, 'አመት': 365}[unit] * n
    if re.search(_DATE_BEFORE, m.group(3)):
        delta = -delta
    target = date.today() + timedelta(days=delta)
    ey, em, ed = gregorian_to_ethiopic(target.year, target.month, target.day)
    if lang == 'en':
        return (f'{n} {unit} from today is {target.strftime("%A, %d %B %Y")} '
                f'({MONTHS[em - 1]} {ed}, {ey} ዓ.ም).')
    wm = weekday(target.year, target.month, target.day)
    gm = GREGORIAN_MONTHS[target.month - 1]
    return (f'ከዛሬ {_fmt(n)} {unit} {"በኋላ" if delta > 0 else "በፊት"} '
            f'{wm}፣ {gm} {target.day} ቀን {target.year} ይሆናል። '
            f'(በኢትዮጵያ አቆጣጠር፦ {MONTHS[em - 1]} {ed}፣ {ey} ዓ.ም)')


def _percentage(text, lang):
    m = re.search(r'(?:በ\s*)?(\d+(?:\.\d+)?)\s*(?:%|በመቶ|percent)', text, re.I)
    if not m:
        return None
    pct = float(m.group(1))
    rest = [v for v in _numbers(text) if v != pct]
    if not rest:
        return None
    base = rest[0]
    result = base * pct / 100
    if lang == 'en':
        return f'{_fmt(pct)}% of {_fmt(base)} is {_fmt(result)}.'
    return f'የ{_fmt(base)} በ{_fmt(pct)} በመቶ {_fmt(result)} ነው። ({_fmt(base)} × {_fmt(pct)} ÷ 100)'


def _average(text, lang):
    if not re.search(_AVG, text, re.I):
        return None
    nums = _numbers(text)
    if len(nums) < 2:
        return None
    avg = sum(nums) / len(nums)
    joined = ' + '.join(_fmt(v) for v in nums)
    if lang == 'en':
        return f'The average of {", ".join(_fmt(v) for v in nums)} is {_fmt(avg)}. ({joined}) ÷ {len(nums)}'
    return f'አማካይ፡ {_fmt(avg)} ነው። ({joined}) ÷ {len(nums)}'


def _comparison(text, lang):
    nums = _numbers(text)
    if len(nums) < 2:
        return None
    if re.search(_DIFF, text, re.I):
        d = abs(nums[0] - nums[1])
        return (f'The difference is {_fmt(d)}. ({_fmt(max(nums[:2]))} − {_fmt(min(nums[:2]))})'
                if lang == 'en' else
                f'ልዩነቱ {_fmt(d)} ነው። ({_fmt(max(nums[:2]))} − {_fmt(min(nums[:2]))})')
    if re.search(_CMP_BIG, text, re.I):
        big = max(nums[:2])
        return (f'{_fmt(big)} is larger.' if lang == 'en'
                else f'ትልቁ {_fmt(big)} ነው። ({_fmt(nums[0])} እና {_fmt(nums[1])} ሲነጻጸሩ)')
    if re.search(_CMP_SMALL, text, re.I):
        small = min(nums[:2])
        return (f'{_fmt(small)} is smaller.' if lang == 'en'
                else f'ትንሹ {_fmt(small)} ነው። ({_fmt(nums[0])} እና {_fmt(nums[1])} ሲነጻጸሩ)')
    return None


def _arithmetic(text, lang):
    nums = _numbers(text)
    if len(nums) < 2:
        return None
    op = None
    for cand in ('sub', 'add', 'mul', 'div'):
        if _cue(text, cand):
            op = cand
            break
    if not op:
        return None
    a, b = nums[0], nums[1]
    if op == 'sub':
        r, sym = a - b, '−'
    elif op == 'add':
        r, sym = a + b, '+'
    elif op == 'mul':
        r, sym = a * b, '×'
    else:
        if b == 0:
            return ('Cannot divide by zero.' if lang == 'en' else 'በዜሮ ማካፈል አይቻልም።')
        r, sym = (a // b if a % b == 0 else round(a / b, 2)), '÷'
    work = f'{_fmt(a)} {sym} {_fmt(b)} = {_fmt(r)}'
    if lang == 'en':
        return f'The answer is {_fmt(r)}. ({work})'
    return f'መልሱ {_fmt(r)} ነው። ({work})'


_WORD_TOK = re.compile(r'[\u1200-\u137f]+|[a-z0-9]+')


def _word_tokens(s):
    return _WORD_TOK.findall((s or '').lower())


def _fact(text, lang):
    """Best-matching curated fact (all words of a key must be present)."""
    words = set(_word_tokens(text))
    if not words:
        return None
    best, best_score = None, 0.0
    for fact in _load_facts():
        keys = fact.get('en', []) if lang == 'en' else fact.get('am', [])
        for k in keys:
            kt = _word_tokens(k)
            if not kt:
                continue
            if len(kt) == 1:
                score = 1.0 if kt[0] in words else 0.0
            else:
                overlap = len(set(kt) & words)
                score = 1.0 if overlap == len(kt) else overlap / len(kt)
            if score > best_score:
                best_score, best = score, fact
    if best and best_score >= 0.75:
        return best.get('answer_en' if lang == 'en' else 'answer_am')
    return None


def solve(text, lang='am'):
    """Return a computed/composed answer for the question, or None."""
    text = (text or '').strip()
    if not text:
        return None
    out = _date_math(text, lang)
    if out:
        return out
    out = _percentage(text, lang)
    if out:
        return out
    out = _average(text, lang)
    if out:
        return out
    out = _comparison(text, lang)
    if out:
        return out
    out = _arithmetic(text, lang)
    if out:
        return out
    out = _fact(text, lang)
    if out:
        return out
    return None


def unknown_reply(text, lang='am'):
    """Honest reply for a fact/number question the data can't ground.

    Never pretends, never returns an unrelated canned essay; instead it states
    the limit and turns it into a useful, teachable exchange.
    """
    text = text or ''
    if not _FACT_Q.search(text):
        return None
    if lang == 'en':
        return ("I don't have that exact fact verified in my own data, so I "
                "won't guess. I can compute math, dates and percentages, look "
                "up Amharic word meanings, and I remember facts you teach me — "
                "say 'remember …' and I'll use it next time.")
    return ('ያንን ትክክለኛ እውነታ በአሁኑ ውሂቤ ውስጥ ማረጋገጥ አልቻልኩም፣ ስለዚህ አልገምትም። '
            'ሂሳብ ማስላት፣ ቀንና ሰዓት፣ በመቶና አማካይ ማስቤ እንዲሁም የአማርኛ ቃላትን መፍታት እችላለሁ። '
            'ትክክለኛውን እውነታ ብትነግረኝ «አስታውስ …» ብለህ አስታውሰውና በሚቀጥለው ጥያቄ እጠቀምበታለሁ።')
