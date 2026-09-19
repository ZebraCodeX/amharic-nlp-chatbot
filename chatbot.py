# -*- coding: utf-8 -*-
"""
chatbot.py — "ዘር", a general-purpose Amharic conversational AI.

An Amharic-speaking AI assistant:
  * vector-based intent matching over `data/knowledge_base.json`
  * Amharic word definitions (built-in dictionary)
  * arithmetic in Amharic or with digits  ("5 ጠቅላላ 3", "17*4")
  * real clock + Amharic date: ስንት ሰዓት ነው? ዛሬ ምን ቀን ነው?
    (Ethiopic calendar: መስከረም 1 … ጳጉሜ, era ዓ.ም, Amharic week-day)
  * fun randomness — coin flip, dice roll, random lot (ዕጣ)
  * remembers your name across the conversation
  * politely enforces "Amharic only"
No Bible, no pastor. Pure Python stdlib.
"""

import json
import os
import random
import re
from datetime import datetime

from amharic_nlp import (
    AmharicNormalizer,
    AmharicTokenizer,
    StopWordFilter,
    AmharicStemmer,
    DocumentIndex,
    TfidfVectorizer,
)
from et_calendar import (
    MONTHS,
    GREGORIAN_MONTHS,
    gregorian_to_ethiopic,
    weekday,
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
# User-generated data lives in a writable dir (a Fly volume can persist it);
# read-only learned artifacts stay in DATA_DIR.
USER_DATA_DIR = os.environ.get('HISAR_USERDATA_DIR') or DATA_DIR
KB_FILE = os.path.join(DATA_DIR, 'knowledge_base.json')
RICH_FILE = os.path.join(DATA_DIR, 'rich_answers.json')
MEMORY_FILE = os.path.join(USER_DATA_DIR, 'user_memory.json')

# Tags whose answers stay short on purpose — chit-chat, identity, courtesy.
SHORT_TAGS = {
    'greeting', 'goodbye', 'thanks', 'how_are_you', 'who_are_you',
    'your_name', 'your_age', 'origin', 'joke', 'praise', 'i_love_you',
    'small_talk',
}

# Question/request words that must not drive intent matching (they appear in
# almost every intent and cause wrong-topic answers). Identity words like
# ማን/የት are kept — they are handled by the identity gate below.
_MATCH_STOP = {
    'ስንት', 'አስረዳኝ', 'ንገረኝ', 'አብራራልኝ',
    'ግለጽልኝ', 'ስጠኝ', 'what', 'which', 'tell', 'explain',
}

# Identity intents only answer when the question is really about Zer — gated on
# their own markers so they can't hijack topical questions on a shared word.
_IDENTITY_RE = {
    'who_are_you': r'ማን\s*ነ(ህ|ሽ|ው|ችሁ|ት)|who\s+are\s+you|what\s+are\s+you',
    'your_name': r'ስም(ህ|ሽ|ዎ)|your\s+name',
    'your_age': r'(እ|ዕ)ድሜ|how\s+old',
    'origin': r'ከየት|የት\s+ነ(ህ|ሽ|ው)|where\s+are\s+you\s+from|ሀገር(ህ|ሽ)',
}
IDENTITY_TAGS = set(_IDENTITY_RE)

# Phrasings that ask for a concise reply, or for an in-depth one.
_SHORT_RE = re.compile(r'በአጭሩ|በአጭር|አጭር|በአጭሩ ንገረኝ|\bshort\b|briefly', re.IGNORECASE)
_DETAIL_RE = re.compile(
    r'በዝርዝር|ዝርዝር|አስረዳኝ|አብራራልኝ|ተጨማሪ\s+ዝርዝር|ሙሉ\s+ማብራሪያ|'
    r'\bdetail|\bin[\s-]?depth|explain',
    re.IGNORECASE)


def normalize_history(history, limit=10):
    """Normalize a conversation history list into {user, reply, source} turns.

    The web client sends OpenAI-style {role, content} turns; the assistant
    stores {user, reply, source}. Accept either (or junk) without crashing.
    """
    out = []
    if not isinstance(history, list):
        return out
    for turn in history[-limit:]:
        if not isinstance(turn, dict):
            continue
        if 'user' in turn and 'reply' in turn:
            user = str(turn.get('user') or '').strip()
            reply = str(turn.get('reply') or '').strip()
            if not user and not reply:
                continue
            out.append({
                'user': user,
                'reply': reply,
                'source': str(turn.get('source') or 'history'),
            })
            continue
        content = str(turn.get('content') or '').strip()
        if not content:
            continue
        if str(turn.get('role') or '') == 'assistant':
            out.append({'user': '', 'reply': content, 'source': 'follow_up'})
        else:
            out.append({'user': content, 'reply': '', 'source': 'injected'})
    return out

# Intents that are creative by nature — routed to the LLM first when one is
# reachable, so the "write a poem / book / website" requests get real output.
CREATIVE_TAGS = {'book_writing', 'story_writing', 'character_creation', 'essay'}

# Amharic number words → digits (helps the calculator)
AMH_NUM_BASE = {
    'ዜሮ': 0,
    'አንድ': 1, 'ሁለት': 2, 'ሦስት': 3, 'ሶስት': 3, 'አራት': 4,
    'አምስት': 5, 'ስድስት': 6, 'ስስት': 6, 'ሰባት': 7,
    'ስምንት': 8, 'ዘጠኝ': 9, 'አስር': 10,
    'ሃያ': 20, 'ሀያ': 20, 'ሰላሳ': 30, 'አርባ': 40, 'ሃምሳ': 50,
    'ስልሳ': 60, 'ሰባ': 70, 'ሰማንያ': 80, 'ዘጠና': 90,
    'መቶ': 100, 'ሺህ': 1000,
}
AMH_DIGITS = {v: k for k, v in [
    ('ዜሮ', 0), ('አንድ', 1), ('ሁለት', 2), ('ሦስት', 3), ('አራት', 4),
    ('አምስት', 5), ('ስድስት', 6), ('ሰባት', 7), ('ስምንት', 8), ('ዘጠኝ', 9),
]}


def _expand_numbers():
    """Add compound Amharic numbers (11..99) to the lookup."""
    d = dict(AMH_NUM_BASE)
    ones = ['አንድ', 'ሁለት', 'ሦስት', 'አራት', 'አምስት',
            'ስድስት', 'ሰባት', 'ስምንት', 'ዘጠኝ']
    tens = [('አስራ', 10), ('ሃያ', 20), ('ሰላሳ', 30), ('አርባ', 40),
            ('ሃምሳ', 50), ('ስልሳ', 60), ('ሰባ', 70), ('ሰማንያ', 80),
            ('ዘጠና', 90)]
    for word, base in tens:
        for i, o in enumerate(ones, start=1):
            d[f'{word} {o}'] = base + i
    return d


AMH_NUM = _expand_numbers()


def _amh_num_word(n):
    """Convert an integer (0..999999) into its Amharic name."""
    if n < 0:
        return 'አሉታዊ ' + _amh_num_word(-n)
    if n < 20:
        return {0: 'ዜሮ', 1: 'አንድ', 2: 'ሁለት', 3: 'ሦስት', 4: 'አራት',
                5: 'አምስት', 6: 'ስድስት', 7: 'ሰባት', 8: 'ስምንት',
                9: 'ዘጠኝ', 10: 'አስር', 11: 'አስራ አንድ', 12: 'አስራ ሁለት',
                13: 'አስራ ሦስት', 14: 'አስራ አራት', 15: 'አስራ አምስት',
                16: 'አስራ ስድስት', 17: 'አስራ ሰባት', 18: 'አስራ ስምንት',
                19: 'አስራ ዘጠኝ'}[n]
    tens = {20: 'ሃያ', 30: 'ሰላሳ', 40: 'አርባ', 50: 'ሃምሳ',
            60: 'ስልሳ', 70: 'ሰባ', 80: 'ሰማንያ', 90: 'ዘጠና'}
    if n >= 1000:
        k, rest = divmod(n, 1000)
        head = 'ሺህ' if k == 1 else _amh_num_word(k) + ' ሺህ'
        return head + ((' ' + _amh_num_word(rest)) if rest else '')
    if n >= 100:
        h, rest = divmod(n, 100)
        head = 'መቶ' if h == 1 else _amh_num_word(h) + ' መቶ'
        return head + ((' ' + _amh_num_word(rest)) if rest else '')
    for t in (90, 80, 70, 60, 50, 40, 30, 20):
        if n >= t:
            rest = n - t
            return tens[t] + ((' ' + _amh_num_word(rest)) if rest else '')
    return str(n)


class AmharicAssistant:
    """The chat brain. Everybody talks to it in Amharic."""

    def __init__(self, knowledge_base_path=KB_FILE):
        self.normalizer = AmharicNormalizer()
        self.tokenizer = AmharicTokenizer()
        self.stemmer = AmharicStemmer()
        self.stop_filter = StopWordFilter(_MATCH_STOP)
        self.data = self._load(knowledge_base_path)
        self.intents = self.data['intents']
        self.dictionary = self.data.get('dictionary', {})
        self.rich = self._load_rich()
        self.name = self.data.get('assistant', {}).get('name', 'ዘር')
        self.user_name = None
        self._lat_re = re.compile(r'[\u0041-\u024f]+')
        self._more_memory = []
        self._index = None
        self._idx_to_tag = []
        self.memory = self._load_memory()
        self._last = None          # (tag, response) of the last KB answer
        self._used_points = {}     # tag -> how many rich bullet points shown
        self._short_requested = False
        self.history = []          # recent turns for deeper context
        self._build_index()

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------
    def _load(self, path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)

    def _load_rich(self):
        """Curated, multi-section detail per intent (summary/points/example)."""
        try:
            with open(RICH_FILE, encoding='utf-8') as f:
                data = json.load(f)
            answers = data.get('answers', {})
            return answers if isinstance(answers, dict) else {}
        except (OSError, ValueError):
            return {}

    def _compose_detailed(self, tag, base):
        """Turn a one-line KB answer into a thorough, structured reply.

        Returns (text, followups). Tags without curated detail (chit-chat,
        identity) keep their short answer unchanged.
        """
        if tag in SHORT_TAGS:
            return base, []
        entry = self.rich.get(tag)
        if not entry:
            return base, []
        parts = [entry.get('summary') or base]
        points = [p for p in (entry.get('points') or []) if p]
        if points:
            parts.append('ዋና ነጥቦች፦\n' + '\n'.join('• ' + p for p in points))
        example = entry.get('example')
        if example:
            parts.append('ምሳሌ፦ ' + example)
        followups = [f for f in (entry.get('followups') or []) if f]
        if followups:
            parts.append('ተጨማሪ ልጠይቅ? ' + ' · '.join(followups))
        return '\n\n'.join(parts), followups

    def _detail_reply(self, tag, base):
        """Detailed reply for a matched intent, honoring a concise request."""
        if self._short_requested:
            return base, []
        return self._compose_detailed(tag, base)

    def _build_index(self):
        docs = []
        tags = []
        for intent in self.intents:
            for pattern in intent['patterns']:
                toks = self._tokens(pattern)
                if toks:
                    docs.append(toks)
                    tags.append(intent['tag'])
        if not docs:
            self._index = None
            return
        self._index = DocumentIndex(docs).build()
        self._idx_to_tag = tags

    def _tokens(self, text):
        norm = self.normalizer.normalize(text)
        toks = self.tokenizer.tokenize(norm)
        toks = self.stop_filter.filter(toks)
        return [self.stemmer.stem(t) for t in toks]

    def _primary_latin(self, text):
        letters = [c for c in text if c.isalpha()]
        if not letters:
            return False
        n_lat = sum(1 for c in letters if '\u0041' <= c <= '\u024f')
        return n_lat / len(letters) > 0.6

    # ------------------------------------------------------------------
    # language gate & helpers
    # ------------------------------------------------------------------
    def _is_amharic_only(self, text):
        return self._primary_latin(text)

    # ------------------------------------------------------------------
    # intent retrieval
    # ------------------------------------------------------------------
    def _match_intent(self, text):
        """Return (tag, score) of the best matching intent via vector search."""
        if self._index is None:
            return None, 0.0
        q = self._tokens(text)
        if not q:
            return None, 0.0
        results = self._index.search(q, k=3)
        if not results:
            return None, 0.0
        for score, idx in results:
            tag = self._idx_to_tag[idx]
            if tag in IDENTITY_TAGS and not re.search(_IDENTITY_RE[tag], text, re.I):
                continue
            return tag, score
        return None, 0.0

    def _build_kw_index(self):
        """token → tags inverted index + per-tag token sets (built once)."""
        index = {}
        tag_tokens = {}
        for intent in self.intents:
            tag = intent['tag']
            toks = set()
            for p in intent['patterns']:
                toks |= set(self._tokens(p))
            tag_tokens[tag] = toks
            for t in toks:
                index.setdefault(t, set()).add(tag)
        self._kw_index = index
        self._kw_tag_tokens = tag_tokens

    def _keyword_intent(self, text):
        """Second-pass intent match weighted by token specificity (1/document
        frequency), so a distinctive word like «እጠብቅ» wins over an ambiguous one.
        Ambiguous-only queries match nothing rather than guessing."""
        if getattr(self, '_kw_index', None) is None:
            self._build_kw_index()
        q = set(self._tokens(text))
        if not q:
            return None, 0.0
        scores = {}
        for tok in q:
            tags = self._kw_index.get(tok)
            if not tags:
                continue
            weight = 1.0 / len(tags)
            for tag in tags:
                if tag in SHORT_TAGS:
                    continue
                scores[tag] = scores.get(tag, 0.0) + weight
        if not scores:
            return None, 0.0
        best = max(scores, key=scores.get)
        overlap = len(q & self._kw_tag_tokens.get(best, set()))
        specific = any(len(self._kw_index.get(tok, ())) == 1
                       for tok in q & self._kw_tag_tokens.get(best, set()))
        total = scores[best]
        # Require a distinctive token or ≥2 shared words.
        if total < 1.0 or not (specific or overlap >= 2):
            return None, 0.0
        return best, min(1.0, total / max(1, len(q)))

    def _try_reason(self, text):
        """Deterministic 'thinking': word problems, comparisons, facts."""
        try:
            import reasoning
        except Exception:
            return None
        return reasoning.solve(text, 'am')

    def _respond_for(self, tag, exclude=None, query=None):
        for intent in self.intents:
            if intent['tag'] == tag:
                pool = [r for r in intent['responses'] if r != exclude]
                if not pool:
                    pool = intent['responses']
                # Stay relevant to the wording, but vary among equally-good
                # phrasings so the same prompt doesn't return byte-identical text.
                if query and len(pool) > 1:
                    qt = set(self._tokens(query))
                    scores = [(len(qt & set(self._tokens(r))), r) for r in pool]
                    top = max(s for s, _ in scores)
                    resp = random.choice([r for s, r in scores if s == top])
                else:
                    resp = random.choice(pool)
                if tag == 'greeting':
                    resp = self._time_greeting() + '! ' + resp
                if self.user_name and tag in ('greeting', 'how_are_you'):
                    return resp.rstrip('?') + f", {self.user_name}?"
                return resp
        return None

    # ------------------------------------------------------------------
    # long-term teachable memory (persisted to data/user_memory.json)
    # ------------------------------------------------------------------
    def _load_memory(self):
        try:
            with open(MEMORY_FILE, encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_memory(self):
        try:
            os.makedirs(os.path.dirname(MEMORY_FILE) or '.', exist_ok=True)
            with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.memory, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _try_teach(self, text):
        m = re.search(r'(አስታውስ|አስታወስ|ትዝ\s+ይበል|ማስታወሻ)', text)
        if not m:
            return None
        before = text[:m.start()].strip()
        after = text[m.end():].strip()
        fact = (after + ' ' + before) if after else before
        fact = re.sub(r'\s+', ' ', fact).strip(' \u1235\u1265\u1361\u12ea!?')
        if len(fact) < 2:
            return None
        self.memory[str(len(self.memory) + 1)] = fact
        self._save_memory()
        return (f"አስታወስኩ! ከአሁን በኋላ «{fact}» ይህንን አስታውሳለሁ። "
                f"ስለ አንተ/ስለ ማንኛውም ርዕስ ብትጠይቅ ከእወቀት እንደዚህ እመልሳለሁ።")

    def _word_set(self, text):
        out = set()
        for w in self._normalize_words(text):
            for p in ('ውስጥ', 'የ', 'ለ', 'በ', 'ከ', 'ዓ', 'ም', 'ነው'):
                if len(w) > 3 and w.startswith(p):
                    w = w[len(p):]
                    break
            out.add(w)
        return out

    def _normalize_words(self, text):
        return re.split(r'[\s፤፥፣።!?፧«»…]+',
                        self.normalizer.normalize(text).strip())

    def _recall_memory(self, text):
        if not self.memory:
            return None
        q = self._word_set(text)
        best, best_score = None, 0
        for fact in self.memory.values():
            fw = self._word_set(fact)
            overlap = len(q & fw)
            if overlap > best_score:
                best, best_score = fact, overlap
        if best_score >= 1:
            return f"ትዝ አለኝ፦ {best}"
        return None

    # ------------------------------------------------------------------
    # follow-ups: answer "እና ታዲያ? / ተጨማሪ" after a KB answer
    # ------------------------------------------------------------------
    def _follow_up(self, text):
        if not self._last:
            return None
        tag, used = self._last
        if not re.search(r'(እና|ታዲያ|ደግሞ|ተጨማሪ|ሌላ|እንዴት|ለምን|ምን ማለት|more|also|then)', text):
            return None
        # Prefer the next unseen bullets from the curated detail, so a follow-up
        # deepens the answer instead of repeating it.
        entry = self.rich.get(tag)
        if entry:
            points = [p for p in (entry.get('points') or []) if p]
            start = self._used_points.get(tag, 0)
            remaining = points[start:]
            if remaining:
                take = remaining[:3]
                self._used_points[tag] = start + len(take)
                out = 'ተጨማሪ ነጥቦች፦\n' + '\n'.join('• ' + p for p in take)
                if start + len(take) >= len(points):
                    example = entry.get('example')
                    if example:
                        out += '\n\nምሳሌ፦ ' + example
                self._last = (tag, used)
                return out
        resp = self._respond_for(tag, exclude=used)
        if resp:
            self._last = (tag, resp)
            return resp
        return None

    # ------------------------------------------------------------------
    # calculator
    # ------------------------------------------------------------------
    def _parse_number(self, tok):
        tok = tok.replace(',', '')
        try:
            return int(float(tok))
        except ValueError:
            pass
        if tok in AMH_NUM:
            return AMH_NUM[tok]
        return None

    def _try_math(self, text):
        t = text.strip()
        pairs = [
            ([' ሲደመር ', ' ጠቅላላ ', ' ሲጨመር ', ' ሲደመሩ '], 'add'),
            ([' ሲቀነስ ', ' ሲጣራ ', ' ቀንስ '], 'sub'),
            ([' ሲባዛ ', ' በ '], 'mul'),
            ([' ሲከፈል ', ' ሲከፋፈል '], 'div'),
        ]
        for seps, op in pairs:
            for sep in seps:
                if sep in t:
                    left, right = t.split(sep, 1)
                    a = self._parse_number(left.strip())
                    b = self._parse_number(right.strip().rstrip('?').rstrip('።'))
                    if a is None or b is None:
                        continue
                    if op == 'div' and b == 0:
                        return 'በዜሮ ማካፈል አይቻልም! ሌላ አካፋይ ስጠኝ።'
                    return self._compute(a, b, op)
        # arabic digits with operators
        m = re.search(r'^([\d,]+)\s*([\+\-\*/x])\s*([\d,]+)\s*=?\s*$', t)
        if m:
            a = int(m.group(1).replace(',', ''))
            b = int(m.group(3).replace(',', ''))
            return self._compute(a, b, {'+': 'add', '-': 'sub', '*': 'mul',
                                        'x': 'mul', '/': 'div'}[m.group(2)], arabic=True)
        # '8 + 4 =' style with words
        m2 = re.search(r'^([አ-፟0-9,]+)\s*([\+\-\*/x])\s*([አ-፟0-9,]+)\s*=?\s*$', t)
        if m2:
            a = self._parse_number(m2.group(1))
            b = self._parse_number(m2.group(3))
            if a is not None and b is not None:
                return self._compute(a, b, {'+': 'add', '-': 'sub', '*': 'mul',
                                            'x': 'mul', '/': 'div'}[m2.group(2)], arabic=True)
        return None

    def _compute(self, a, b, op, arabic=False):
        if op == 'add':
            r = a + b
            word = _amh_num_word(r)
            return f"መልሱ፡ {r} — በአማርኛ {word}"
        if op == 'sub':
            r = a - b
            word = _amh_num_word(r)
            return f"መልሱ፡ {r} — በአማርኛ {word}"
        if op == 'mul':
            r = a * b
            word = _amh_num_word(r)
            return f"መልሱ፡ {r} — በአማርኛ {word}"
        if b == 0:
            return 'በዜሮ ማካፈል አይቻልም።'
        if a % b == 0:
            r = a // b
            word = _amh_num_word(r)
            return f"መልሱ፡ {r} — በአማርኛ {word}"
        r = round(a / b, 2)
        return f"መልሱ፡ {r}"

    # ------------------------------------------------------------------
    # word meaning lookup
    # ------------------------------------------------------------------
    def _try_dict(self, text):
        # «word» … → meaning
        m = re.search(r'«([^«»]{1,30})»', text)
        if m and m.group(1) in self.dictionary:
            w = m.group(1)
            return f"«{w}» ማለት፡ {self.dictionary[w]}"
        # word ምን ማለት ነው / ምን ማለት ነው word / word ትርጉም
        m = re.search(r'([\u1200-\u137f]{2,20})\s+ምን\s+ማለት\s+ነው[።? ]*$', text)
        if not m:
            m = re.search(r'ምን\s+ማለት\s+ነው\s+([\u1200-\u137f]{2,20})[።? ]*$', text)
        if not m:
            m = re.search(r'([\u1200-\u137f]{2,20})\s+(ማለት|ትርጉም)', text)
        if m:
            w = m.group(1).strip()
            if w in self.dictionary:
                return f"«{w}» ማለት፡ {self.dictionary[w]}"
        return None

    # ------------------------------------------------------------------
    # user name capture
    # ------------------------------------------------------------------
    def _try_name(self, text):
        m = re.search(r'ስሜ\s+([\u1200-\u137f]{2,20})', text)   # ስሜ …
        if m and not text.startswith('ስምህ'):
            self.user_name = m.group(1)
            return f"{self.user_name} ብለህ ትጠራለህ? ደስ ተሰኝቻለሁ! ሰላም {self.user_name}! እንዴት ልረዳህ?"
        return None

    # ------------------------------------------------------------------
    # real clock, Amharic (Ethiopic) calendar date & fun randomness
    # ------------------------------------------------------------------
    def _time_greeting(self):
        h = datetime.now().hour
        if 5 <= h < 12:
            return 'መልካም ጥዋት'
        if 12 <= h < 16:
            return 'እንደቀኑ ውብ ቀን'
        if 16 <= h < 19:
            return 'መልካም ምሽት'
        return 'መልካም ሌሊት'

    def _amh_clock(self, h, m):
        eth = (h + 6) % 12 or 12
        if m == 0:
            tail = ''
        elif m <= 30:
            tail = ' ተኩል' if m == 30 else f' እና {_amh_num_word(m)} ደቂቃ'
        else:
            tail = f' እና {_amh_num_word(m)} ደቂቃ'
        part = ('ሌሊት' if h < 4 else 'ጧት' if h < 11 else 'ቀትር'
                if h < 14 else 'ከሰዓት' if h < 18 else 'ማታ' if h < 21 else 'ሌሊት')
        return f'{_amh_num_word(eth)} ሰዓት{tail} ({part})'

    def _try_time(self, text):
        if not re.search(r'(ሰዓት|ሰአት|ሰዓቱ|ጊዜ(ው)?\s*(ስንት|ምን))', text):
            return None
        if not re.search(r'(ስንት|ምን\s+ያህል|ምን\s+ያክል|አሳይ|ንገረኝ|መቼ)\??', text):
            return None
        now = datetime.now()
        return (f'አሁን {self._amh_clock(now.hour, now.minute)} ነው። '
                f'ለአንድ ግልጽነት (24-ሰዓት: {now.hour:02d}:{now.minute:02d})።')

    def _try_date(self, text):
        if not re.search(r'(ዛሬ|ቀኑ|ቀን|ሳምንቱ|ሳምንት|የምን\s+ቀን|የትኛው\s+ቀን)', text):
            return None
        if not re.search(r'(ስንት|ምን|የምን|የትኛው|አሳይ|መቼ)\??', text):
            return None
        now = datetime.now()
        et = gregorian_to_ethiopic(now.year, now.month, now.day)
        wd = weekday(now.year, now.month, now.day)
        suffix = ' ቀን' if et[1] != 13 else ''
        return (f'ዛሬ {wd} ነው። በኢትዮጵያ አቆጣጠር {MONTHS[et[1] - 1]} {et[2]}{suffix}, {et[0]} ዓ.ም። '
                f'በጎርጎርዮስ አቆጣጠር {GREGORIAN_MONTHS[now.month - 1]} {now.day}, {now.year}።')

    _RANDOM_RE = re.compile(
        r'ሳንቲም\s+(ጣል|ጣሊ|ጣሉ|\btoss\b)|\bcoin\b|\bflip\b|'
        r'(ዳይስ|ዲይስ)\b|\bdice\b|\bdie\b|'
        r'ዕጣ|ዕድል\s+(ቅዳ|ጣል)|\blot\b|'
        r'(random\s+)?(number|ቁጥር)\s+(ምረጥ|random)|\brandom\b|የዘፈቀደ\s+ቁጥር',
        re.IGNORECASE)

    def _try_random(self, text):
        m = self._RANDOM_RE.search(text)
        if not m:
            return None
        if re.search(r'(ሳንቲም|\bcoin\b|\bflip\b)', text, re.I):
            return f'ሳንቲሙ {random.choice(["ጭንቅላት", "ጅራት"])} ወጣ!'
        if re.search(r'(ዳይስ|ዲይስ|\bdice\b|\bdie\b)', text, re.I):
            return f'ዳይሱ {random.randint(1, 6)} ወጣ! (ጥሩ ዕድል?)'
        if re.search(r'(random|የዘፈቀደ|ቁጥር)', text, re.I):
            return random.randint(1, 100) == 7 and '…(ዕጣው 7 — ዕድለኛ ቁጥር!)' or f'ዕጣው {random.randint(1, 100)} ወጣ!'
        return f'ዕጣው {random.randint(1, 100)} ወጣ!'

    # ------------------------------------------------------------------
    # mini code generator: ፕሮግራም / programming language snippets
    # ------------------------------------------------------------------
    def _detect_lang(self, text):
        lang_words = {
            'python': ['ፓይቶን', 'ፒቶን', 'ፒዮን', 'python', 'py '],
            'javascript': ['ጃቫስክሪፕት', 'ጄኤስ', 'js', 'javascript', 'node'],
            'html': ['ኤችቲኤምኤል', 'html', 'ድረገፅ', 'web page', 'ገፅ'],
            'css': ['ሲኤስኤስ', 'css', 'ቅጥ'],
            'json': ['ጃሶን', 'json'],
            'bash': ['ሼል', 'ስክሪፕት', 'bash', 'shell', 'linux'],
        }
        for lang, words in lang_words.items():
            if any(w in text for w in words):
                return lang
        return None

    @staticmethod
    def _snippets_all():
        return [
            (('sort', 'አሰላለል', 'አስተካክል', 'order', 'ደረደር'), 'python',
             "def sort_values(values):\n    return sorted(values)\n\n"
             "numbers = [42, 7, 1997, 1]\n"
             "print(sort_values(numbers))  # Output: [1, 7, 42, 1997]"),
            (('loop', 'ሉፕ', 'መደጋገም', 'for', 'while', 'ድገም'), 'python',
             "# for loop\nfor i in range(1, 6):\n    print(f'{i}. ሰላም ዓለም')\n\n"
             "# while loop\ncount = 0\nwhile count < 3:\n    print('Hello!')\n    count += 1"),
            (('file', 'ፋይል', 'አንብብ', 'read', 'write', 'ጻፍ', 'ፅሁፍ'), 'python',
             "# Read a text file (UTF-8)\nwith open('notes.txt', encoding='utf-8') as f:\n"
             "    content = f.read()\nprint(content)\n\n"
             "# Write a text file\nwith open('notes.txt', 'w', encoding='utf-8') as f:\n"
             "    f.write('ሰላም ዓለም')"),
            (('csv', 'ሠንጠረዥ', 'ውሂብ', 'data'), 'python',
             "import csv\n\nwith open('data.csv', encoding='utf-8') as f:\n"
             "    rows = list(csv.reader(f))\n"
             "    for row in rows[:5]:\n        print(row)"),
            (('server', 'ሰርቨር', 'ዌብ', 'web', 'ስርቨር'), 'python',
             "from http.server import HTTPServer, SimpleHTTPRequestHandler\n\n"
             "server = HTTPServer(('0.0.0.0', 8000), SimpleHTTPRequestHandler)\n"
             "print('Serving on port 8000…')\nserver.serve_forever()"),
            (('json', 'ጃሶን'), 'python',
             "import json\n\ndata = {'name': 'ዘር', 'age': 1}\n"
             "print(json.dumps(data, ensure_ascii=False, indent=2))\n\n"
             "parsed = json.loads(json.dumps(data))\nprint(parsed['name'])"),
            (('html', 'ገፅ', 'page', 'ድር', 'ድረ'), 'html',
             "<!doctype html>\n<html lang='am'>\n<head>\n"
             "<meta charset='utf-8'>\n<title>ሰላም ዓለም</title>\n</head>\n<body>\n"
             "  <h1>ሰላም ዓለም!</h1>\n  <button onclick=\"alert('ሰላም!')\">ንካኝ</button>\n"
             "</body>\n</html>"),
            (('css', 'ቅጥ', 'style', 'ስታይል'), 'css',
             "body {\n  font-family: 'Noto Sans Ethiopic', sans-serif;\n"
             "  background: #0f3460;\n  color: #fff;\n}\n\n"
             "button:hover {\n  opacity: 0.8;\n}"),
            (('javascript', 'js ', 'ጃቫስክሪፕት', 'function'), 'javascript',
             "function greet(name) {\n  return `ሰላም ${name}!`;\n}\n\n"
             "console.log(greet('ሰሎሜ'));\n\n"
             "const nums = [5, 2, 9, 1];\nconsole.log(nums.sort((a, b) => a - b));"),
            (('bash', 'ሼል', 'ስክሪፕት', 'linux', 'ሊኑክስ'), 'bash',
             "#!/usr/bin/env bash\nfor name in ማርያም አበበ ሰሎሜ; do\n"
             "  echo \"ሰላም $name!\"\ndone\n\nls -la"),
        ]

    @staticmethod
    def _default_snippet(lang):
        defaults = {
            'python': "def main():\n    # እዚህ ጋር ኮድህን ጻፍ\n    print('ሰላም ዓለም!')\n\n"
                      "if __name__ == '__main__':\n    main()",
            'javascript': "function main() {\n  // ኮድህን እዚህ ጻፍ\n"
                          "  console.log('ሰላም ዓለም!');\n}\n\nmain();",
            'html': "<!doctype html>\n<html lang='am'>\n<head>\n<meta charset='utf-8'>\n"
                    "<title>ገፄ</title>\n</head>\n<body>\n  <h1>ሰላም!</h1>\n</body>\n</html>",
            'css': "body {\n  font-family: 'Noto Sans Ethiopic', sans-serif;\n}",
            'json': "{\n  \"name\": \"ዘር\",\n  \"topic\": \"AI\",\n  \"lang\": \"am\"\n}",
            'bash': "#!/usr/bin/env bash\necho 'ሰላም ዓለም!'",
        }
        return defaults.get(lang, defaults['python'])

    def _try_code(self, text):
        # Offline Amharic code generator first — real code with Amharic
        # comments and identifiers, no model required.
        try:
            from codegen import generate as _codegen
            rich = _codegen(text)
            if rich:
                return rich
        except Exception:
            pass
        low = self.normalizer.normalize(text)
        action = re.search(
            r'(\b(ጻፍ|ፃፍ|ፅፍ|ጻፍልኝ|ፃፍልኝ|ስጠኝ|እጽፋለሁ|እፅፋለሁ|write|make|help me|generate)\b|ኮድ|ስክሪፕት)', low)
        if not action:
            return None
        lang = self._detect_lang(low)
        if lang is None and not self._primary_latin(low):
            return None
        lang = lang or 'python'
        snippet = None
        for words, slang, code in self._snippets_all():
            if any(w in low for w in words):
                snippet = code
                break
        if snippet is None:
            snippet = self._default_snippet(lang)
        art = 'አንድ' if lang not in ('css', 'json') else ''
        return (f"በ{lang} ፕሮግራም ለመጻፍ እነሆ {art} ምሳሌ፦\n"
                f"በአንተ ፕሮጀክት መሰረት ቀይረህ ተጠቀምበት። የምትፈልገውን ተግባር ከገለፅክልኝ ኮዱን አዘጋጅቼ እሰጥሃለሁ።\n\n{snippet}")

    # ------------------------------------------------------------------
    # fallback
    # ------------------------------------------------------------------
    def _fallback(self):
        return random.choice([
            "አድርጌ አላየሁም ይሆናል። ስለ ምን ነገር ነው የምትጠይቀው? በአማርኛ በዝርዝር ስጠኝ።",
            "ያንን ጥያቄ ይዘቱን በተሻለ መረዳት እፈልጋለሁ። ተጨማሪ ዝርዝር ስጠኝ፣ ወይም እንዲህ ጠይቀኝ፡- «ስለ ቴክኖሎጂ ንገረኝ»፣ «AI ምንድን ነው?»፣ «5 ጠቅላላ 7»",
            "ለመርዳት እዚህ ነኝ! ስለ ማንኛውም ርዕስ ጠይቀኝ፣ ሂሳብ አስላ፣ ወይም የአማርኛ ቃላትን ፍቺ ጠይቅ። ለምሳሌ፡ «ሳይንስ ምንድን ነው?»",
        ])

    # ------------------------------------------------------------------
    # optional LLM brain (llm.py) — used for creative / open-ended requests
    # ------------------------------------------------------------------
    def _llm_answer(self, text, on_delta=None):
        try:
            from llm import chat as llm_chat
            from llm import chat_stream as llm_chat_stream
        except Exception:
            return None
        system = (
            "አንተ ዘር ነህ፣ ብልህና ዝርዝር የምትመልስ የአማርኛ ቋንቋ AI ረዳት ነህ። "
            "ሁልጊዜ በአማርኛ (ግዕዝ ፊደል) መልስ ስጥ። ለእንግሊዝኛ መልስ አትስጥ፣ ትርጉም ብቻ "
            "ከጠየቀህ በስተቀር። "
            "መልስህ ጥልቅና ዝርዝር ይሁን፦ (፩) በአንድ ዓረፍተ ነገር አጭር መግቢያ/ ትርጉም ስጥ፤ "
            "(፪) ከዚያ «ዋና ነጥቦች» በሚል ርዕስ ስር 3–6 የተለያዩ ነጥቦችን በነጥብ (•) ዘርዝር፤ "
            "(፫) ተጨባጭ ምሳሌ ወይም አጠቃቀም ጨምር፤ (፬) ሲመችህ ሠንጠረዥ፣ ደረጃ ወይም ኮድ "
            "ተጠቀም፤ (፭) በመጨረሻ አንባቢው ሊጠይቅ የሚችለውን 1–2 ተከታይ ጥያቄ ጠቁም። "
            "ተጠቃሚው ግጥም፣ ዘፈን፣ ታሪክ፣ ድርሰት፣ ቻራክተር፣ ድረ-ገጽ (HTML) ወይም ኮድ "
            "ከጠየቀ ሙሉ ይዘቱን አዘጋጅ። ወዳጃዊ፣ ግልጽና ፈጠራ አስተሳሰብ ያለህ ሁን። "
            "አስፈላጊ ካልሆነ ከ600 ቃላት አትርግም (ግጥም/ኮድ/ዝርዝር ሲሆን ተገቢውን ሙሉ ክፍል ስጥ)።"
        )
        if self._short_requested:
            system += " ተጠቃሚው አጭር መልስ ጠይቋል — አጭርና ቀጥተኛ መልስ ስጥ።"
        if self.user_name:
            system += f" የተጠቃሚው ስም {self.user_name} ነው።"
        try:
            from learning import hints as _learned_hints
            learned = _learned_hints(text)
            if learned:
                system += (" የተጠቃሚው የትርጉም ትምህርት (እነዚህን ቃላት በተጠቃሚው መሰረት "
                           "ተጠቀም)፦ " + "; ".join(learned) + "።")
        except Exception:
            pass
        history = []
        for turn in self.history[-6:]:
            if not isinstance(turn, dict):
                continue
            user = str(turn.get('user') or '').strip()
            if user:
                history.append({'role': 'user', 'content': user})
            src = str(turn.get('source') or '')
            reply = str(turn.get('reply') or '').strip()
            if reply and (src.startswith('intent:') or src in
                          ('fallback', 'llm', 'follow_up', 'injected', 'history')):
                history.append({'role': 'assistant', 'content': reply})
        if on_delta:
            parts = []
            for delta in llm_chat_stream(system, text, history):
                if delta:
                    parts.append(delta)
                    on_delta(delta)
            return ''.join(parts).strip() or None
        return llm_chat(system, text, history)

    def _creative_offline(self, text):
        """Offline generative skills: write/create/develop/plan get REAL output
        (poems, plans, websites…) even when no LLM is reachable."""
        try:
            from creative import creative_answer
            return creative_answer(text)
        except Exception:
            return None

    # ------------------------------------------------------------------
    # main entry point
    # ------------------------------------------------------------------
    @staticmethod
    def _result(reply, source, confidence, followups=None, detail=False):
        out = {'reply': reply, 'source': source,
               'confidence': round(confidence, 3) if isinstance(confidence, float) else confidence}
        if followups:
            out['followups'] = list(followups)
        if detail:
            out['detail'] = True
        return out

    def respond(self, text, use_llm=True, detail=True, on_delta=None):
        text = (text or '').strip()
        if not text:
            return self._result('ምን ትፈልጋለህ? በአማርኛ ጻፍልኝ።', 'empty', 1.0)

        # Respect an explicit call for a short or an in-depth answer.
        self._short_requested = bool(_SHORT_RE.search(text))
        if _DETAIL_RE.search(text):
            self._short_requested = False
            detail = True

        # code requests may contain programing-language names (Latin) → allow
        code = self._try_code(text)
        if code:
            self._push_history(text, code, 'code')
            return self._result(code, 'code', 0.9)

        if self._is_amharic_only(text):
            return self._result(
                'እባክህ በአማርኛ ጻፍልኝ! እኔ የተፈጠርኩት የአማርኛ ቋንቋን ለመረዳት ነው። እንግሊዝኛን አልገባኝም። ትርጉም የምትፈልግ ከሆነ «EN» ማብሪያውን ተጠቀም።',
                'language_gate', 1.0)

        # teachable long-term memory
        taught = self._try_teach(text)
        if taught:
            self._push_history(text, taught, 'memory')
            return self._result(taught, 'memory', 0.9)

        # name capture
        named = self._try_name(text)
        if named:
            return self._result(named, 'name', 0.9)

        # arithmetic
        math = self._try_math(text)
        if math:
            return self._result(math, 'math', 0.99)

        # reasoning: word problems, comparisons, dates, curated facts
        reasoned = self._try_reason(text)
        if reasoned:
            self._push_history(text, reasoned, 'reasoning')
            return self._result(reasoned, 'reasoning', 0.95)

        # real clock / Amharic date / fun randomness
        clock = self._try_time(text)
        if clock:
            return self._result(clock, 'time', 0.95)
        day = self._try_date(text)
        if day:
            return self._result(day, 'date', 0.95)
        rnd = self._try_random(text)
        if rnd:
            return self._result(rnd, 'random', 0.9)

        # word meaning
        meaning = self._try_dict(text)
        if meaning:
            return self._result(meaning, 'dictionary', 0.95)

        # knowledge base (vector search, then a keyword fallback)
        tag, score = self._match_intent(text)
        if not (tag and score >= 0.30):
            ktag, kscore = self._keyword_intent(text)
            if ktag and kscore >= 0.5:
                tag, score = ktag, max(score, kscore)
        if tag and score >= 0.30:
            resp = self._respond_for(tag, query=text)
            self._last = (tag, resp)
            rule_only = tag in ('greeting', 'how_are_you', 'goodbye', 'thanks')
            prefers_llm = (use_llm and not rule_only and
                           (tag in CREATIVE_TAGS or
                            self._is_creative_request(text) or
                            self._is_open_ended(text) or
                            bool(_DETAIL_RE.search(text))))
            if prefers_llm:
                llm_reply = self._llm_answer(text, on_delta=on_delta)
                if llm_reply:
                    self._push_history(text, llm_reply, 'llm')
                    return self._result(llm_reply, 'llm', 0.9)
                offline = self._creative_offline(text)
                if offline:
                    self._push_history(text, offline, 'creative')
                    return self._result(offline, 'creative', 0.7)
            detailed, followups = (self._detail_reply(tag, resp) if detail
                                   else (resp, []))
            self._push_history(text, detailed, f'intent:{tag}')
            return self._result(detailed, f'intent:{tag}', score,
                                followups=followups, detail=detailed != resp)

        # deep recall: facts the user taught me
        recalled = self._recall_memory(text)
        if recalled:
            self._push_history(text, recalled, 'memory')
            return self._result(recalled, 'memory', 0.5)

        # context follow-up on the previous topic
        follow = self._follow_up(text)
        if follow:
            self._push_history(text, follow, 'follow_up')
            return self._result(follow, 'follow_up', 0.6)

        # deeply open-ended question → LLM first, rule fallback last
        if use_llm:
            llm_reply = self._llm_answer(text)
            if llm_reply:
                self._push_history(text, llm_reply, 'llm')
                return self._result(llm_reply, 'llm', 0.85)
            if self._is_creative_request(text):
                offline = self._creative_offline(text)
                if offline:
                    self._push_history(text, offline, 'creative')
                    return self._result(offline, 'creative', 0.7)

        return self._result(self._resolve_fallback(text), 'fallback', 0.12,
                            followups=self._fallback_followups())

    def _resolve_fallback(self, text):
        """For a factual/number question we can't ground, say so honestly
        instead of returning an unrelated generic line."""
        try:
            import reasoning
            honest = reasoning.unknown_reply(text, 'am')
        except Exception:
            honest = None
        return honest or self._fallback()

    def _fallback_followups(self):
        return ['ስለ AI ንገረኝ', 'ስለ ቴክኖሎጂ ንገረኝ', 'ስለ ኢትዮጵያ ንገረኝ']

    def _push_history(self, user, reply, source):
        self.history.append({'user': user, 'reply': reply, 'source': source})
        del self.history[:-10]

    def _is_creative_request(self, text):
        return bool(re.search(
            r'(ግጥም|ዘፈን|መዝሙር|ድርሰት|ድህረ\s*ገጽ|ዌብ\s*ሳይት|ቻራክተር|ተረት|ልቦለድ|'
            r'እቅድ|ዕቅድ|ፕላን|ዲዛይን|ግንባታ|ፍጠር|ፍጥረት|አዘጋጅ|'
            r'poem|song|story|essay|website|plan|design|build|create|develop|write|generate|'
            r'ታሪክ\s+(ጻፍ|ፃፍ|ስጠኝ)|ጻፍልኝ|ፃፍልኝ|ፃፍ|ጻፍ|ስጠኝ|ጻፍልኝ)',
            self.normalizer.normalize(text)))

    def _is_open_ended(self, text):
        """„Tell me about…" phrasing — deserves the LLM when one is reachable."""
        return bool(re.search(
            r'ንገረኝ|ንገርኝ|ጠይቀኝ|ጠይቁ|ምን\s+ታውቃለህ|ምን\s+ታውቂያለሁ|'
            r'ተረዳህ|ልታስረዳኝ|ማብራራት|መጠየቅ\s+እፈልጋለሁ|ጥያቄ\s+አለኝ|'
            r'ምን\s+ማለት\s+ነው\s+.*\?|ስለ.*\?\s*$',
            self.normalizer.normalize(text)))


def demo_chat():
    """Interactive command-line chat session in Amharic."""
    print("ዘር — የአማርኛ AI ረዳት. አማርኛን ጻፍልኝ (‹ደህና ሁን› በል ወይም Ctrl-C ለመውጣት).")
    assistant = AmharicAssistant()
    print("ዝግጁ ነው! አሁን ማውራት እንጀምር።\n")
    while True:
        try:
            user = input('አንተ  > ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nደህና ሁን!')
            break
        if not user:
            continue
        if user.lower() in ('quit', 'exit', 'q'):
            print('ዘር > ደህና ሁን! እንደገና ይገናኘን።')
            break
        r = assistant.respond(user)
        print(f'ዘር > {r["reply"]}')


if __name__ == '__main__':
    demo_chat()
