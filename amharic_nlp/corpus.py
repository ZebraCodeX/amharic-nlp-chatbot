# -*- coding: utf-8 -*-
"""
corpus.py — stream readers for free Amharic text sources.

Every reader is a generator of sentence strings, so training can limit how
much of each source it ingests (great for huge dumps like CC-100). Supported
formats:

  * bible        — amharic-bible-json (magna25/amharic-bible-json). Yields verses.
  * plaintext    — your own UTF-8 .txt/.md/.srt books, subtitles, articles.
                   111 sentence-per-line is preserved; long paragraphs are
                   split with `amharic_nlp.SentenceSplitter`.
  * leipzig      — Leipzig Corpora Collection sentence files. Lines look like
                   `<id>\\t<sentence>`, tabs separate id from text
                   (file name patterns: `*_sentences.txt`).
  * wiki_xml     — Amharic Wikipedia dump (`amwiki-*pages-articles*.xml(.bz2)`).
                   Strips MediaWiki markup; yields article *paragraph* text.
  * cc100        — CC-100 `am.txt.xz` (one sentence-ish per line, web crawl).

Pure stdlib (bz2, gzip, lzma do the decompression; bz2/xz corpora are streamed).
"""

import bz2
import gzip
import json
import lzma
import os
import re

from .toolkit import SentenceSplitter

_WS_TAGS = re.compile(r'<[^>]+>')
_WIKI_LINKS = re.compile(r'\[\[([^\]|]*)(?:\|[^\]]*)?\]\]')
_TPL = re.compile(r'\{\{[^{}]*\}\}')
_HEADERS = re.compile(r'^\s*=+.*?=+\s*$', re.MULTILINE)
_COMMENT = re.compile(r'<!--.*?-->', re.S)


def _open_maybe(path):
    """Open a text file, transparently decompressing .gz/.bz2/.xz."""
    if path.endswith('.gz'):
        return gzip.open(path, 'rt', encoding='utf-8', errors='replace')
    if path.endswith('.bz2'):
        return bz2.open(path, 'rt', encoding='utf-8', errors='replace')
    if path.endswith('.xz'):
        return lzma.open(path, 'rt', encoding='utf-8', errors='replace')
    return open(path, encoding='utf-8', errors='replace')


def plaintext(path, splitter=None):
    """Yield sensible sentence strings from a plain UTF-8 text file."""
    splitter = splitter or SentenceSplitter()
    with _open_maybe(path) as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if len(line) <= 240 and not line.endswith(('።', '፡', '፧', '!', '?')):
                yield line
                continue
            for s in splitter.split(line):
                yield s


def leipzig(path, splitter=None):
    """Yield sentences from a Leipzig corpus file (`<id>\\t<sentence>`)."""
    splitter = splitter or SentenceSplitter()
    with _open_maybe(path) as f:
        for raw in f:
            line = raw.rstrip('\n')
            if not line:
                continue
            if '\t' in line:
                line = line.split('\t', 1)[1]
            s = line.strip()
            if not s:
                continue
            if len(s) <= 240:
                yield s
            else:
                for part in splitter.split(s):
                    yield part


def wiki_xml(path):
    """Yield article paragraph text from an Amharic Wikipedia dump XML.

    The pipeline `amwiki-latest-pages-articles.xml(.bz2)` steps through
    <page><revision><text>…</text> blocks; MediaWiki markup is stripped.
    """
    with _open_maybe(path) as f:
        cur = []
        in_text = False
        for raw in f:
            if '<text' in raw or in_text:
                if in_text:
                    cur.append(raw.rstrip('\n'))
                else:
                    cur.append(raw.split('<text', 1)[1])
                if '</text>' not in raw:
                    in_text = True
                    continue
                in_text = False
                page = '\n'.join(cur)
                cur = []
                for para in _clean_wikitext(page):
                    yield para
        if cur:
            for para in _clean_wikitext('\n'.join(cur)):
                yield para


def _clean_wikitext(text):
    """Strip MediaWiki markup, returning non-empty paragraphs."""
    text = _COMMENT.sub(' ', text)
    # keep text through the first </text> boundary (multiple pages merged okay)
    idx = text.find('</text>')
    if idx != -1:
        text = text[:idx]
    text = _WS_TAGS.sub(' ', text)
    text = _TPL.sub(' ', text)
    text = _WIKI_LINKS.sub(r'\1', text)
    text = _HEADERS.sub(' ', text)
    # drop tables/reference leftover noise
    text = re.sub(r'\{\|[^{}]*\}', ' ', text)
    paras = [p.strip() for p in re.split(r'\n+', text) if p.strip()]
    return paras


def cc100(path, splitter=None):
    """Yield lines from a CC-100 style Amharic crawl file (one line per line)."""
    splitter = splitter or SentenceSplitter()
    with _open_maybe(path) as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if len(line) <= 240:
                yield line
            else:
                for part in splitter.split(line):
                    yield part


def bible(path):
    """Yield verse strings from an amharic-bible-json file."""
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    for book in data.get('books', []):
        for ch in book.get('chapters', []):
            for v in ch.get('verses', []):
                if isinstance(v, str) and v.strip():
                    yield v.strip()


_READERS = {
    'plaintext': plaintext,
    'leipzig': leipzig,
    'wiki_xml': wiki_xml,
    'cc100': cc100,
    'bible': bible,
}


def iter_corpus_dir(domain_dir, splitter=None, limit=None):
    """Yield sentences from every text file under a corpus domain directory —
    or from a single file, when given a concrete file path.

    Format is auto-detected: files named `*_sentences*.txt` / `*.tsv` are
    Leipzig-style; dumps containing `pages-articles` are Wikipedia XML; other
    files are read as plain UTF-8 text. `limit` caps the total sentences.
    """
    if not os.path.exists(domain_dir):
        return
    splitter = splitter or SentenceSplitter()
    files = [domain_dir] if os.path.isfile(domain_dir) else sorted(
        os.path.join(domain_dir, n)
        for n in os.listdir(domain_dir)
        if os.path.isfile(os.path.join(domain_dir, n))
        and not n.endswith('.gitkeep'))
    seen = 0
    for path in files:
        name = os.path.basename(path)
        if name.endswith('.json'):
            continue  # json handled explicitly (bible), not as raw text
        if 'pages-articles' in name:
            gen = wiki_xml(path)
        elif '_sentences' in name or name.endswith('.tsv'):
            gen = leipzig(path, splitter)
        else:
            gen = plaintext(path, splitter)
        for sent in gen:
            yield sent
            seen += 1
            if limit and seen >= limit:
                return