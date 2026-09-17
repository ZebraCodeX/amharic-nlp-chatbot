#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
download_corpora.py — fetch free Amharic text sources into corpora/.

Where each source lands (all are free / openly licensed for research):

  books/    amharic-bible-json (wordproject Amharic Bible, Open Bible license)
            amwiki-latest-pages-articles.xml.bz2 (Wikipedia CC BY-SA)
  articles/ BBC Amharic article text (source text, public-service broadcast)
            amh_wikipedia_2021_100K + amh_news_public_2020_100K
            (Leipzig Corpora Collection — free Amharic corpora; their CDN
            bot-blocks scripts, so a plain `curl` or browser pre-download is
            expected: just drop the *_sentences.txt files into corpora/articles/)
  other/    cc-100 Amharic crawl (Common Crawl based, ~139 MB)

Movies/subtitles: no stable open mirror was reachable (the OPUS object store
is currently down), so drop your own UTF-8 subtitle or script .txt files into
`amharic_nlp/corpora/movies/` — the trainer picks them up automatically.

Usage:
    python3 -m amharic_nlp.tools.download_corpora            # everything
    python3 -m amharic_nlp.tools.download_corpora --skip-cc100
    python3 -m amharic_nlp.tools.download_corpora --sources bible,wiki,bbc
    python3 -m amharic_nlp.tools.download_corpora --bbc-articles 50

Pure stdlib. Idempotent: already-downloaded files are skipped.
"""

import argparse
import os
import re
import sys
import tarfile
import urllib.request

from .. import CORPORA_DIR

BASE = 'https://wortschatz.uni-leipzig.de/download'
WIKI_URL = 'https://dumps.wikimedia.org/amwiki/latest/amwiki-latest-pages-articles.xml.bz2'
BIBLE_URL = ('https://raw.githubusercontent.com/magna25/amharic-bible-json/main/'
             'amharic_bible.json')
CC100_URL = 'https://data.statmt.org/cc-100/am.txt.xz'

SOURCES = {
    # name:  (url, subdir, display, extract?, big?)
    'bible': (BIBLE_URL, 'books', 'Amharic Bible', False, False),
    'wiki': (WIKI_URL, 'books', 'Amharic Wikipedia (dump)', False, False),
    'leipzig': (BASE + '/amh_wikipedia_2021_100K.tar.gz', 'articles',
                'Leipzig amh-wikipedia-100K', True, False),
    'news': (BASE + '/amh_news_public_2020_100K.tar.gz', 'articles',
             'Leipzig amh-news-100K', True, False),
    'web': (BASE + '/amh_web_public_2020_250K.tar.gz', 'other',
            'Leipzig amh-web-250K', True, False),
    'cc100': (CC100_URL, 'other', 'CC-100 Amharic crawl (139 MB)', False, True),
}

_UA = 'Mozilla/5.0  Amharic-NLP-trainer/2.0'
_ARGS = None


def _download(url, dest):
    print(f'  downloading {url}')
    req = urllib.request.Request(url, headers={'User-Agent': _UA})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, 'wb') as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    mb = os.path.getsize(dest) / 1e6
    print(f'  saved {dest} ({mb:.1f} MB)')


def _extract_leipzig(tarball, dest_dir):
    """Pull every *_sentences.txt out of a Leipzig tar.gz bundle.

    Some CDNs hand out an HTML bot-check page instead of the tarball — detect
    that and remove the bogus file so a re-run can retry cleanly.
    """
    try:
        tar = tarfile.open(tarball, 'r:gz')
    except tarfile.TarError:
        print(f'  [warn] {tarball} is not a real tar.gz (bot-check page?) — '
              'download it in a browser and drop the *_sentences.txt files in '
              f'{dest_dir}')
        os.remove(tarball)
        return
    count = 0
    with tar:
        for member in tar.getmembers():
            if member.isfile() and '_sentences' in member.name:
                f = tar.extractfile(member)
                name = os.path.basename(member.name)
                out = os.path.join(dest_dir, name)
                with open(out, 'wb') as o:
                    o.write(f.read())
                count += 1
    print(f'  → {count} Leipzig sentence file(s) into {dest_dir}')


_ETHIOPIC = re.compile(r'[\u1200-\u135a]')
_ABS_ARTICLE = re.compile(r'href="(https://www\.bbc\.com/amharic/articles/[a-z0-9]+)"')
_REL_ARTICLE = re.compile(r'href="(/amharic/articles/[a-z0-9]+)"')
_TOPIC = re.compile(r'href="(/amharic/topics/[a-z0-9]+)"')


def fetch_bbc(target_dir, max_articles=40):
    """Download Amharic BBC article text (public-service news source).

    Walks the BBC Amharic index → topic pages → article pages, extracting <p>
    paragraphs, and saves one plain-text file per article under target_dir.
    """
    os.makedirs(target_dir, exist_ok=True)
    ua = {'User-Agent': _UA}

    def get(url):
        req = urllib.request.Request(url, headers=ua)
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode('utf-8', 'replace')

    print('  fetching BBC Amharic index')
    html = get('https://www.bbc.com/amharic')
    links = [m.group(1) for m in _ABS_ARTICLE.finditer(html)]
    topics = [m.group(1) for m in _TOPIC.finditer(html)]
    print(f'  index: {len(links)} articles, {len(topics)} topic pages')
    for t in topics[:10]:
        try:
            topic_html = get('https://www.bbc.com' + t)
        except Exception:
            continue
        links += [m.group(1) for m in _ABS_ARTICLE.finditer(topic_html)]
    # de-duplicate, prefer article ids found anywhere
    links = list(dict.fromkeys(links))
    print(f'  {len(links)} unique articles (fetching up to {max_articles})')
    saved = 0
    for url in links[:max_articles]:
        slug = re.sub(r'[^a-z0-9]+', '-', url).strip('-')
        out = os.path.join(target_dir, f'bbc_{slug}.txt')
        if os.path.exists(out):
            continue
        try:
            body = get(url)
        except Exception:
            continue
        paras = [p for p in re.findall(r'<p[^>]*>(.*?)</p>', body, re.S)
                 if _ETHIOPIC.search(p)]
        if not paras:
            continue
        clean = []
        for p in paras:
            t = re.sub(r'<[^>]+>', ' ', p)
            t = re.sub(r'\s+', ' ', t).strip()
            if t and len(t) > 1:
                clean.append(t)
        if not clean:
            continue
        with open(out, 'w', encoding='utf-8') as f:
            f.write('\n\n'.join(clean) + '\n')
        saved += 1
    print(f'  → {saved} BBC Amharic article text file(s) into {target_dir}')
    return saved


def fetch(name, cache_dir=os.path.join(CORPORA_DIR)):
    if name == 'bbc':
        return fetch_bbc(os.path.join(cache_dir, 'articles'),
                         max_articles=_ARGS.bbc_articles)
    url, subdir, label, extract, big = SOURCES[name]
    target_dir = os.path.join(cache_dir, subdir)
    os.makedirs(target_dir, exist_ok=True)
    fname = url.rsplit('/', 1)[-1]
    if fname.endswith('.tar.gz'):
        fname = name + '.tar.gz'
    dest = os.path.join(target_dir, fname)
    if os.path.exists(dest):
        print(f'[skip] {label} already present ({dest})')
        return dest
    print(f'[{label}]')
    _download(url, dest)
    if extract:
        _extract_leipzig(dest, target_dir)
    return dest


def main():
    ap = argparse.ArgumentParser(description='Download free Amharic corpora.')
    ap.add_argument('--sources', default='bible,wiki,bbc,cc100',
                    help='comma list of: ' + ','.join(SOURCES) + ',bbc')
    ap.add_argument('--skip-cc100', action='store_true',
                    help='do not fetch the big CC-100 crawl')
    ap.add_argument('--bbc-articles', type=int, default=40,
                    help='how many BBC Amharic articles to fetch (default 40)')
    ap.add_argument('--corpora', default=CORPORA_DIR, help='corpora root')
    args = ap.parse_args()
    global _ARGS
    _ARGS = args

    wanted = [s.strip() for s in args.sources.split(',') if s.strip()]
    if args.skip_cc100:
        wanted = [s for s in wanted if s != 'cc100']

    print(f'Corpus root: {args.corpora}')
    for name in wanted:
        if name not in SOURCES and name != 'bbc':
            print(f'[warn] unknown source {name!r} — skipping')
            continue
        fetch(name, cache_dir=args.corpora)

    print('\nDone. Now train with:  python3 -m amharic_nlp.training')


if __name__ == '__main__':
    main()