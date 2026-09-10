# -*- coding: utf-8 -*-
"""
amharic_nlp.py — A pure-Python NLP toolkit for the Amharic (Ge'ez) language.

Provides:
  * AmharicNormalizer   – collapses homophone letter classes (ሀ/ሐ/ኀ → ሀ)
  * AmharicTokenizer    – splits Amharic running text into words
  * AmharicStemmer      – rule-based morphological stemmer (agglutinative
                          prefixes/suffixes of Amharic)
  * StopWordFilter      – removes Amharic function words
  * SentenceSplitter    – segments text on Amharic sentence punctuation
  * TfidfVectorizer     – lightweight TF-IDF + cosine similarity (no numpy)
  * DocumentIndex       – top-k retrieval over a corpus
  * BibleCorpus         – loads Amharic Bible verses and builds a searchable index

Designed to run with only the Python standard library, fully offline.
"""

import json
import math
import os
import re
from collections import Counter

# ---------------------------------------------------------------------------
# Character classes
# ---------------------------------------------------------------------------

# Amharic uses several Ge'ez letters that have merged in pronunciation.
# Normalizing them to one canonical representative improves matching.
NORMALIZATION = {
    # Ha-row variants → ሀ
    '\u1210': '\u1200', '\u1211': '\u1201', '\u1212': '\u1202',
    '\u1213': '\u1203', '\u1214': '\u1204', '\u1215': '\u1205', '\u1216': '\u1206',
    # ኀ-row variants → ሀ (same 7 orders)
    '\u1280': '\u1200', '\u1281': '\u1201', '\u1282': '\u1202',
    '\u1283': '\u1203', '\u1284': '\u1204', '\u1285': '\u1205', '\u1286': '\u1206',
    # ሠ-row variants → ሰ
    '\u1220': '\u1230', '\u1221': '\u1231', '\u1222': '\u1232',
    '\u1223': '\u1233', '\u1224': '\u1234', '\u1225': '\u1235', '\u1226': '\u1236',
    # ኣ → አ (same sound, alternate orthography)
    '\u12a3': '\u12a0',
    # ፀ-row variants → ጸ
    '\u12f8': '\u12e0', '\u12f9': '\u12e1', '\u12fa': '\u12e2',
    '\u12fb': '\u12e3', '\u12fc': '\u12e4', '\u12fd': '\u12e5', '\u12fe': '\u12e6',
}

# Ethiopic letters only (U+1200–U+135A); punctuation/numerals live above U+1360
ETHIOPIC_RE = re.compile(r'[\u1200-\u135a]+')

# Common Amharic punctuation that can be stripped around words
PUNCTUATION = '።፡፣፥፤፨፧፦!?;:،«»"' + "'" + '()[]{},.'


# ---------------------------------------------------------------------------
# Default Amharic stopwords
# ---------------------------------------------------------------------------

DEFAULT_STOPWORDS = {
    'እና', 'ነው', 'ላይ', 'ውስጥ', 'ውስጣቸው', 'ወደ', 'ከ', 'ለ', 'በ', 'የ',
    'እንደ', 'ያህል', 'ጋር', 'ከፊት', 'በኋላ', 'ሁሉ', 'ሁሉም', 'ምን', 'ግን',
    'አንድ', 'አንዱ', 'አንዲት', 'እንዲህ', 'እንዲሁም', 'ወይም', 'እስከ', 'ሆነ',
    'ሆኑ', 'ሆኗል', 'ማለት', 'ይህ', 'ይህም', 'ያ', 'ያን', 'እንዴት', 'ምንም',
    'ብቻ', 'እዚህ', 'እዚያ', 'ሁልጊዜ', 'በመሆኑ', 'አሁን', 'ብዙ', 'በዚህ',
    'በዚህም', 'ያለ', 'ስለ', 'ደግሞ', 'አንደ', 'አለ', 'አለች', 'አሉ', 'አለኝ',
    'ነበር', 'ነበሩ', 'ነበረች', 'ሳለ', 'ጊዜ', 'ቀን', 'እስኪ', 'ዘንድ', 'እስከአሁን',
    'መሆኑ', 'በማድረግ', 'ሊሆን', 'ሆኖ', 'ሆነው', 'ነገር', 'ነገሮች', 'ሰው', 'ሰዎች',
    'ቤት', 'ቤቱ', 'እኛ', 'አንተ', 'አንቺ', 'እርሱ', 'እሷ', 'እነሱ', 'ራሱ', 'ራሷ',
    'ለምን', 'ፊት', 'ፊትህ', 'ዙሪያ', 'በኩል', 'መካከል', 'ውጭ', 'ሳይሆን', 'አለበት',
    'በምንም', 'ምክንያት', 'ምክንያቱም', 'ከዚህ', 'ከዚያ', 'ከነዚህ', 'እንደዚህ', 'እንደዚያ',
    'በዚያ', 'በዚህ', 'እነዚህ', 'እነዚያ', 'ሌላ', 'ሌሎች', 'ዛሬ', 'ነገ', 'ትናንት',
    'ሰዓት', 'ወቅት', 'ዕለት', 'ዓመት', 'ወር', 'አመት', 'ዘመን', 'አሁንም', 'እንደገና',
    'ወይ', 'እንጂ', 'እንኳ', 'እንኳን', 'ብቻም', 'እስካሁን', 'ድረስ', 'ጋርም', 'ናቸው',
    'ሆነላቸው', 'አላቸው', 'ተጨማሪ', 'አንዴ', 'ሁለት', 'ሦስት', 'አራት', 'አምስት',
    'ትንሽ', 'ትልቅ', 'ጥሩ', 'መልካም', 'ፍጹም', 'ክፉ', 'ቶሎ', 'ቀስ', 'ቀስቀስ',
    'የሚል', 'የሚሉ', 'የሚለው', 'የሆነ', 'የሆኑ', 'ያለው', 'ያላቸው', 'ቢሆን',
}


# ---------------------------------------------------------------------------
# Rule-based stemmer
# ---------------------------------------------------------------------------

# Agglutinative prefixes (longest first so greedy stripping is safe-ish).
# Amharic prepositions & relative markers commonly fused to word stems.
STEM_PREFIXES = [
    '\u12a5\u1235\u12a8',   # እስከ (until)
    '\u12a5\u1295\u12f0',   # እንደ (like/as)
    '\u12a8\u1235\u1270',   # ከስተ (within, from)
    '\u1295\u1235\u1270',   # ንስተ (nisătä-)
    '\u12e8\u121a',         # የሚ (relative present)
    '\u12e8\u121d',         # የም (relative, colloquial)
    '\u12eb\u120b',         # ያላ (negative relative)
    '\u1235\u1208',         # ስለ (about/for)
    '\u12c8\u12f0',         # ወደ (to/towards)
    '\u12a5\u1290',         # እነ (plural person-word prefix)
]

# Common derived/plural suffixes (longest first).
STEM_SUFFIXES_CLEAN = [
    '\u12ce\u127d\u1295',   # ዎችን (plural + accusative)
    '\u122e\u127d',         # ሮች (plural, e.g. ነገሮች)
    '\u12ce\u127d',         # ዎች (plural)
    '\u127d\u1295',         # ችን (plural + accusative)
    '\u12a3\u1275',         # ኣት (plural, e.g. ሀገራት)
    '\u12a3\u1295',         # ኣን (plural, e.g. መምህራን)
    '\u12cd\u1295',         # ውን (definite + accusative)
    '\u1215\u1275',         # ሕት (nominalization)
    '\u127d',               # ች (plural/definiteness, e.g. ልጆች)
]

MIN_STEM_LENGTH = 2


class AmharicNormalizer:
    """Collapses homophone letter classes into one canonical representative."""

    def __init__(self):
        self._map = str.maketrans(NORMALIZATION)

    def normalize(self, text):
        return text.translate(self._map)


class AmharicTokenizer:
    """Splits running Amharic text into word tokens."""

    def __init__(self):
        self._re = ETHIOPIC_RE

    def tokenize(self, text):
        return self._re.findall(text.lower())


class AmharicStemmer:
    """Conservative rule-based stemmer using prefix/suffix stripping."""

    def max_munch(self, word, affixes, side):
        """Strip the longest matching affix, at most once per round."""
        if side == 'pre':
            for aff in sorted(affixes, key=len, reverse=True):
                if word.startswith(aff) and len(word) - len(aff) >= MIN_STEM_LENGTH:
                    return word[len(aff):]
        else:
            for aff in sorted(affixes, key=len, reverse=True):
                if word.endswith(aff) and len(word) - len(aff) >= MIN_STEM_LENGTH:
                    return word[:-len(aff)]
        return word

    def stem(self, word):
        """Return a normalized, affix-stripped form of `word`."""
        rounds = 2
        stem = word
        for _ in range(rounds):
            new = self.max_munch(stem, STEM_PREFIXES, 'pre')
            new = self.max_munch(new, STEM_SUFFIXES_CLEAN, 'suf')
            if new == stem:
                break
            stem = new
        return stem


class StopWordFilter:
    """Removes Amharic function words."""

    def __init__(self, additional=None):
        self.stopwords = set(DEFAULT_STOPWORDS)
        if additional:
            self.stopwords |= set(additional)

    def is_stop(self, word):
        return word in self.stopwords

    def filter(self, words):
        return [w for w in words if not self.is_stop(w) and len(w) >= 2]


class SentenceSplitter:
    """Segments text on Amharic full stops and question marks."""

    def __init__(self):
        self._re = re.compile(r'(?<=[\u1200-\u137f])\s*([።፡፧፨!?])\s*(?=[\u1200-\u137f]|$)', re.UNICODE)

    def split(self, text):
        parts = re.split(r'[\u1225\u1233።፡፧፨!?]', text)
        return [p.strip() for p in parts if p.strip()]


class TfidfVectorizer:
    """Minimal TF-IDF implementation (no numpy)."""

    def __init__(self, min_df=1, sublinear_tf=True):
        self.min_df = min_df
        self.sublinear_tf = sublinear_tf
        self.vocab = {}
        self.idf = {}
        self._trained = False

    def _terms(self, doc):
        return doc  # expected as list of pre-processed tokens

    def fit(self, docs):
        self._n_docs = len(docs)
        df = Counter()
        for doc in docs:
            for term in set(doc):
                df[term] += 1
        self.vocab = {t: i for i, t in enumerate(df)}
        self.idf = {t: math.log((self._n_docs + 1) / (c + 1)) + 1.0
                    for t, c in df.items() if c >= self.min_df}
        self._trained = True
        return self

    def transform(self, doc):
        tf = Counter(doc)
        vec = {}
        norm = 0.0
        for term, count in tf.items():
            if term not in self.idf:
                continue
            w = (1 + math.log(count)) if self.sublinear_tf else count
            w *= self.idf[term]
            vec[term] = w
            norm += w * w
        norm = math.sqrt(norm) or 1.0
        return {t: w / norm for t, w in vec.items()}

    @staticmethod
    def cosine(a, b):
        if not a or not b:
            return 0.0
        if len(a) > len(b):
            a, b = b, a
        dot = 0.0
        for t, w in a.items():
            if t in b:
                dot += w * b[t]
        return dot  # vectors are already L2-normalized


class DocumentIndex:
    """Indexes a corpus of texts for top-k cosine retrieval."""

    def __init__(self, docs, vectorizer=None):
        self.docs = docs
        if vectorizer is None:
            vectorizer = TfidfVectorizer()
        self.vectorizer = vectorizer
        self.vectors = None
        self._built = False

    def build(self):
        token_docs = [self._prep(d) for d in self.docs]
        self.vectorizer.fit(token_docs)
        self.vectors = [self.vectorizer.transform(td) for td in token_docs]
        self._built = True
        return self

    def _prep(self, text):
        # Default preprocessing pipeline (subclass for custom behaviour)
        return text  # already token list form, override at call site

    def search(self, query, k=5):
        qvec = self.vectorizer.transform(query)
        scored = []
        for idx, vec in enumerate(self.vectors):
            s = TfidfVectorizer.cosine(qvec, vec)
            if s > 0.0:
                scored.append((s, idx))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:k]


class BibleCorpus:
    """
    Loads the Amharic Bible (magna25/amharic-bible-json format) and builds a
    TF-IDF inverted index for topic-based verse retrieval.
    """

    def __init__(self, bible_path, tokenizer_cls=None, use_cache=True, cache_dir=None):
        self.raw_verses = []          # list of (book, chapter, verse_no, text)
        self.verses = []              # plain text list (parallel with vectors)
        self._tokenizer = AmharicTokenizer()
        if tokenizer_cls is None:
            tokenizer_cls = AmharicTokenizer
        self.normalizer = AmharicNormalizer()
        self.stemmer = AmharicStemmer()
        self.stopfilter = StopWordFilter()
        self.bible_path = bible_path
        self.n_documents = 0
        self.inverted_index = None    # term -> {doc_id: tf}
        self.df = None                # term -> document frequency
        self.use_cache = use_cache
        self.cache_dir = cache_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'data')

    # -- loading ------------------------------------------------------------
    def load(self):
        with open(self.bible_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        verses = []
        for book in data['books']:
            title = book.get('title', '')
            for ch in book['chapters']:
                ch_no = ch.get('chapter', 0)
                for i, v in enumerate(ch['verses']):
                    if v and isinstance(v, str) and v.strip():
                        verses.append((title, ch_no, i + 1, v.strip()))
        self.raw_verses = verses
        self.verses = [ (f'{a} {b}:{c}', d) for a, b, c, d in verses ]
        self.n_documents = len(verses) if verses else len(self.verses)
        return self

    def tokens(self, text):
        norm = self.normalizer.normalize(text)
        toks = self._tokenizer.tokenize(norm)
        toks = self.stopfilter.filter(toks)
        return [self.stemmer.stem(t) for t in toks]

    def save_index(self, path):
        if self.inverted_index is None:
            return
        payload = {
            'verses': self.verses,
            'index': {t: [list(p) for p in pd.items()] for t, pd in self.inverted_index.items()},
            'df': self.df,
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False)

    def load_index(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        self.verses = payload['verses']
        self.n_documents = len(self.verses)
        self.inverted_index = {t: {int(d): tf for d, tf in items}
                               for t, items in payload['index'].items()}
        self.df = payload['df']
        return self

    # -- indexing -----------------------------------------------------------
    def build_index(self):
        """Build a term → {doc_id: tf} inverted index over all verses."""
        index = {}
        df = Counter()
        for doc_id, verse in enumerate(self.verses):
            _ref, verse_text = verse
            toks = self.tokens(verse_text)
            if not toks:
                continue
            tf = Counter(toks)
            for t in set(toks):
                index.setdefault(t, {})[doc_id] = tf[t]
            for t in set(toks):
                df[t] += 1
        self.inverted_index = index
        self.df = df
        return self

    def search(self, query, k=5):
        """Return top-k verses for `query`: [(score, verse_text), ...]"""
        if self.inverted_index is None:
            self.build_index()
        q_toks = self.tokens(query)
        qtf = Counter(q_toks)
        n = max(self.n_documents, 1)
        scores = {}
        for t, qcount in qtf.items():
            post = self.inverted_index.get(t)
            if not post:
                continue
            idf = math.log((n + 1) / (self.df.get(t, 1) + 1)) + 1.0
            qw = (1 + math.log(qcount)) * idf
            for doc, tf in post.items():
                dw = (1 + math.log(tf)) * idf * idf * qw
                scores[doc] = scores.get(doc, 0.0) + dw
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:max(k, 1)]
        return [(score, self.verses[doc]) for doc, score in ranked]


class AmharicTextProcessor:
    """High-level pipeline mirroring classic NLP pre-processing steps."""

    def __init__(self, load_stopwords_from_file=None):
        self.normalizer = AmharicNormalizer()
        self.tokenizer = AmharicTokenizer()
        self.stemmer = AmharicStemmer()
        self.splitter = SentenceSplitter()
        stopwords = set()
        if load_stopwords_from_file and os.path.exists(load_stopwords_from_file):
            with open(load_stopwords_from_file, encoding='utf-8') as f:
                stopwords = {line.strip() for line in f if line.strip()}
        self.stopfilter = StopWordFilter(stopwords)

    def process(self, text):
        norm = self.normalizer.normalize(text)
        tokens = self.tokenizer.tokenize(norm)
        stops = self.stopfilter.filter(tokens)
        stems = [self.stemmer.stem(t) for t in stops]
        return {
            'sentence_count': len(self.splitter.split(text)),
            'tokens': tokens,
            'non_stop': stops,
            'stems': stems,
            'word_freq': dict(Counter(stems).most_common(10)),
        }

    def analyze(self, text):
        """Convenience wrapper returning a readable analysis dict."""
        return self.process(text)