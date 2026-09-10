# -*- coding: utf-8 -*-
"""
chatbot.py — "ሕሳር", a general-purpose Amharic conversational AI.

Like a small ChatGPT that only speaks Amharic:
  * vector-based intent matching over `data/knowledge_base.json`
  * Amharic word definitions (built-in dictionary)
  * arithmetic in Amharic or with digits  ("5 ጠቅላላ 3", "17*4")
  * remembers your name across the conversation
  * politely enforces "Amharic only"
No Bible, no pastor. Pure Python stdlib.
"""

import json
import os
import random
import re

from amharic_nlp import (
    AmharicNormalizer,
    AmharicTokenizer,
    StopWordFilter,
    AmharicStemmer,
    DocumentIndex,
    TfidfVectorizer,
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
KB_FILE = os.path.join(DATA_DIR, 'knowledge_base.json')

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
    for t in (90, 80, 70, 60, 50, 40, 30, 20):
        if n >= t:
            rest = n - t
            return tens[t] + ((' ' + _amh_num_word(rest)) if rest else '')
    if n >= 1000:
        k, rest = divmod(n, 1000)
        head = 'ሺህ' if k == 1 else _amh_num_word(k) + ' ሺህ'
        return head + ((' ' + _amh_num_word(rest)) if rest else '')
    if n >= 100:
        h, rest = divmod(n, 100)
        head = 'መቶ' if h == 1 else _amh_num_word(h) + ' መቶ'
        return head + ((' ' + _amh_num_word(rest)) if rest else '')
    return str(n)


class AmharicAssistant:
    """The chat brain. Everybody talks to it in Amharic."""

    def __init__(self, knowledge_base_path=KB_FILE):
        self.normalizer = AmharicNormalizer()
        self.tokenizer = AmharicTokenizer()
        self.stemmer = AmharicStemmer()
        self.stop_filter = StopWordFilter()
        self.data = self._load(knowledge_base_path)
        self.intents = self.data['intents']
        self.dictionary = self.data.get('dictionary', {})
        self.name = self.data.get('assistant', {}).get('name', 'ሕሳር')
        self.user_name = None
        self._lat_re = re.compile(r'[\u0041-\u024f]+')
        self._more_memory = []
        self._index = None
        self._idx_to_tag = []
        self._build_index()

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------
    def _load(self, path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)

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
        top_score, top_idx = results[0]
        tag = self._idx_to_tag[top_idx]
        return tag, top_score

    def _respond_for(self, tag):
        for intent in self.intents:
            if intent['tag'] == tag:
                item = intent
                resp = random.choice(item['responses'])
                # personalize greetings with the known user name
                if self.user_name and tag in ('greeting', 'how_are_you'):
                    resp = resp.rstrip('?') + f", {self.user_name}?"
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
        # word ምን ማለት ነው / word ትርጉም / word ትርጉም ስጠኝ
        m = re.search(r'([\u1200-\u137f]{2,20})\s+ምን\s+ማለት\s+ነው[።? ]*$', text)
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
    # fallback
    # ------------------------------------------------------------------
    def _fallback(self):
        return random.choice([
            "አድርጌ አላየሁም ይሆናል። ስለ ምን ነገር ነው የምትጠይቀው? በአማርኛ በዝርዝር ስጠኝ።",
            "ያንን ጥያቄ ይዘቱን በተሻለ መረዳት እፈልጋለሁ። ተጨማሪ ዝርዝር ስጠኝ፣ ወይም እንዲህ ጠይቀኝ፡- «ስለ ቴክኖሎጂ ንገረኝ»፣ «AI ምንድን ነው?»፣ «5 ጠቅላላ 7»",
            "እንደ ChatGPT ለመርዳት እዚህ ነኝ! ስለ ማንኛውም ርዕስ ጠይቀኝ፣ ሂሳብ አስላ፣ ወይም የአማርኛ ቃላትን ፍቺ ጠይቅ። ለምሳሌ፡ «ሳይንስ ምንድን ነው?»",
        ])

    # ------------------------------------------------------------------
    # main entry point
    # ------------------------------------------------------------------
    def respond(self, text):
        text = (text or '').strip()
        if not text:
            return {'reply': 'ምን ትፈልጋለህ? በአማርኛ ጻፍልኝ።', 'source': 'empty', 'confidence': 1.0}

        if self._is_amharic_only(text):
            return {
                'reply': 'እባክህ በአማርኛ ጻፍልኝ! እኔ የተፈጠርኩት የአማርኛ ቋንቋን ለመረዳት ነው። እንግሊዝኛን አልገባኝም።',
                'source': 'language_gate', 'confidence': 1.0,
            }

        # name capture
        named = self._try_name(text)
        if named:
            return {'reply': named, 'source': 'name', 'confidence': 0.9}

        # arithmetic
        math = self._try_math(text)
        if math:
            return {'reply': math, 'source': 'math', 'confidence': 0.99}

        # word meaning
        meaning = self._try_dict(text)
        if meaning:
            return {'reply': meaning, 'source': 'dictionary', 'confidence': 0.95}

        # knowledge base (vector search)
        tag, score = self._match_intent(text)
        if tag and score >= 0.30:
            resp = self._respond_for(tag)
            return {'reply': resp, 'source': f'intent:{tag}', 'confidence': round(score, 3)}

        return {'reply': self._fallback(), 'source': 'fallback', 'confidence': 0.12}


def demo_chat():
    """Interactive command-line chat session in Amharic."""
    print("ሕሳር — የአማርኛ AI ረዳት. አማርኛን ጻፍልኝ (‹ደህና ሁን› በል ወይም Ctrl-C ለመውጣት).")
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
            print('ሕሳር > ደህና ሁን! እንደገና ይገናኘን።')
            break
        r = assistant.respond(user)
        print(f'ሕሳር > {r["reply"]}')


if __name__ == '__main__':
    demo_chat()