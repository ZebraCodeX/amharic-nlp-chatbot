#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_corpus.py — collect + clean a large Amharic pretraining corpus.

This is the data layer for *continued pretraining* of an open base model (not
the small QLoRA chat adapter). It streams openly-licensed Amharic sources,
normalises and filters them, deduplicates exactly, and writes gzipped text
shards plus a manifest with licence + size + token counts.

    python3 training/corpus/build_corpus.py --out ~/amharic-corpus \
        --sources wikipedia,cc100,fineweb2,mc4,culturax,opus_tatoeba,bible,local \
        --max-gb-per-source 8 --tokenizer Qwen/Qwen2.5-1.5B-Instruct

Sources are declared in SOURCES with their licence and URL. Each source is
resumable and capped, so a huge crawl can be ingested gradually.

Reality check: a genuinely frontier-scale run needs 10^22–10^25 FLOPs and
trillions of tokens. Amharic has far less text than English, so the realistic
goal here is *the largest legal Amharic corpus* (single-digit billions of
tokens) for continued pretraining + instruction tuning of a 7B–14B open base —
which is exactly where a small team can beat the big models on Amharic.
"""
import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
import urllib.request
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ETH = re.compile(r'[\u1200-\u137f]')
NOT_ETH_PUNCT = re.compile(r'[^\u1200-\u137f\s.,!?;:()\'"\-–—…\u1361-\u1368\u135f0-9]')
WS = re.compile(r'\s+')
TAGS = re.compile(r'<[^>]+>')
URL = re.compile(r'https?://\S+')

OPUS = 'https://object.pouta.csc.fi'

SOURCES = {
    'wikipedia': {
        'kind': 'hf', 'path': 'wikimedia/wikipedia', 'config': '20231101.am',
        'split': 'train', 'text': ['text'], 'lang': 0.5,
        'license': 'CC BY-SA 4.0',
        'url': 'https://huggingface.co/datasets/wikimedia/wikipedia',
    },
    'fineweb2': {
        'kind': 'hf', 'path': 'HuggingFaceFW/fineweb-2', 'config': 'amh_Ethi',
        'split': 'train', 'text': ['text'], 'lang': 0.4,
        'license': 'ODC-BY 1.0',
        'url': 'https://huggingface.co/datasets/HuggingFaceFW/fineweb-2',
    },
    'mc4': {
        'kind': 'hf', 'path': 'mc4', 'config': 'am', 'split': 'train',
        'text': ['text'], 'lang': 0.4, 'trust_remote_code': True,
        'license': 'ODC-BY 1.0 (mC4)',
        'url': 'https://huggingface.co/datasets/mc4',
    },
    'culturax': {
        'kind': 'hf', 'path': 'uonlp/CulturaX', 'config': 'am', 'split': 'train',
        'text': ['text'], 'lang': 0.4, 'repair_mojibake': True,
        'license': 'mixed (mC4 ODC-BY, OSCAR)',
        'url': 'https://huggingface.co/datasets/uonlp/CulturaX',
    },
    'cc100': {
        'kind': 'cc100', 'url': 'https://data.statmt.org/cc-100/am.txt.xz',
        'lang': 0.4, 'license': 'CC-100 / Common Crawl terms',
    },
    'opus_tatoeba': {
        'kind': 'opus', 'zip': f'{OPUS}/OPUS-Tatoeba/v2023-04-12/moses/am-en.txt.zip',
        'member': '.am', 'lang': 0.3, 'license': 'CC BY 2.0 FR',
    },
    'opus_ted2020': {
        'kind': 'opus', 'zip': f'{OPUS}/OPUS-TED2020/v1/moses/am-en.txt.zip',
        'member': '.am', 'lang': 0.3, 'license': 'CC BY-NC-ND 4.0 (TED)',
    },
    'opus_gnome': {
        'kind': 'opus', 'zip': f'{OPUS}/OPUS-GNOME/v1/moses/am-en.txt.zip',
        'member': '.am', 'lang': 0.3, 'license': 'GPL / free software',
    },
    'opus_ubuntu': {
        'kind': 'opus', 'zip': f'{OPUS}/OPUS-Ubuntu/v14.10/moses/am-en.txt.zip',
        'member': '.am', 'lang': 0.3, 'license': 'free software (Launchpad)',
    },
    'bible': {
        'kind': 'bible',
        'path': os.path.join(REPO, 'amharic_nlp', 'corpora', 'books',
                             'amharic_bible.json'),
        'lang': 0.3, 'license': 'public domain / Open Bible',
    },
    'local': {
        'kind': 'local', 'path': os.path.join(REPO, 'amharic_nlp', 'corpora'),
        'lang': 0.2, 'license': 'mixed (user-supplied + repo corpora)',
    },
}


def log(msg):
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def norm_text(text):
    if not text:
        return ''
    text = text.replace('\u00a0', ' ').replace('\u200b', '')
    text = TAGS.sub(' ', text)
    text = URL.sub(' ', text)
    text = WS.sub(' ', text).strip()
    return text


def is_amharic(text, ratio):
    if len(text) < 20:
        return False
    am = len(ETH.findall(text))
    if am < 10:
        return False
    return am >= len(text) * ratio


def shard_stream(out_dir, source, shard_docs):
    os.makedirs(out_dir, exist_ok=True)
    index = 0
    while True:
        path = os.path.join(out_dir, f'part-{index:05d}.txt.gz')
        if not os.path.exists(path):
            break
        index += 1
    return index


class ShardWriter:
    def __init__(self, root, source, shard_docs, tokenizer, dedup, dedup_max,
                 token_sample=1):
        self.dir = os.path.join(root, source)
        self.shard_docs = shard_docs
        self.tokenizer = tokenizer
        self.token_sample = max(1, token_sample)
        self.dedup = dedup
        self.dedup_max = dedup_max
        self.seen = set()
        self.docs = 0
        self.tokens = 0
        self.bytes = 0
        self.raw_bytes = 0
        self.shards = []
        self._fh = None
        self._count = 0
        self._tk = 0
        self._index = shard_stream(self.dir, source, shard_docs)
        self._open()

    def _open(self):
        self.path = os.path.join(self.dir, f'part-{self._index:05d}.txt.gz')
        self._index += 1
        self._fh = gzip.open(self.path, 'wt', encoding='utf-8')
        self._count = 0
        self.shards.append(self.path)

    def _rotate(self):
        self._fh.close()
        self.bytes = sum(os.path.getsize(p) for p in self.shards)
        self._open()

    def add(self, text):
        if self.dedup and len(self.seen) < self.dedup_max:
            digest = hashlib.sha1(text.encode('utf-8')).digest()
            if digest in self.seen:
                return False
            self.seen.add(digest)
        self._fh.write(text.replace('\n', ' ').strip() + '\n')
        self.docs += 1
        self._count += 1
        self._tk += 1
        if self.tokenizer is not None:
            if self._tk % self.token_sample == 0:
                n = len(self.tokenizer(text, add_special_tokens=False)['input_ids'])
                self.tokens += n * self.token_sample
        else:
            self.tokens += max(1, len(ETH.findall(text)) // 2)
        if self._count >= self.shard_docs:
            self._rotate()
        return True

    def close(self):
        if self._fh is not None:
            self._fh.close()
            self._fh = None
        self.bytes = sum(os.path.getsize(p) for p in self.shards)
        return {'shards': self.shards, 'docs': self.docs,
                'tokens': self.tokens, 'bytes': self.bytes}


def download(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        return dest
    log(f'  downloading {url.rsplit("/", 1)[-1]} …')
    req = urllib.request.Request(url, headers={'User-Agent': 'Zer-corpus/1.0'})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, 'wb') as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return dest


def iter_hf(cfg):
    from datasets import load_dataset
    kw = {'split': cfg.get('split', 'train'), 'streaming': True}
    if cfg.get('trust_remote_code') or cfg.get('use_auth'):
        kw['trust_remote_code'] = True
    if cfg.get('use_auth'):
        kw['use_auth_token'] = True
    ds = load_dataset(cfg['path'], cfg.get('config'), **kw)
    fields = cfg.get('text') or ['text']
    repair = cfg.get('repair_mojibake')
    for row in ds:
        for field in fields:
            val = row.get(field)
            if isinstance(val, str) and val.strip():
                if repair:
                    try:
                        fixed = val.encode('latin-1').decode('utf-8')
                        if fixed.count('\u1200') or len(fixed) > len(val):
                            val = fixed
                    except (UnicodeError, ValueError):
                        pass
                yield val
                break


def iter_cc100(cfg, cache):
    import lzma
    path = download(cfg['url'], os.path.join(cache, 'cc100_am.txt.xz'))
    with lzma.open(path, 'rt', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if line:
                yield line


def iter_opus(cfg, cache):
    path = download(cfg['zip'], os.path.join(cache, os.path.basename(cfg['zip'])))
    with zipfile.ZipFile(path) as z:
        name = next((n for n in z.namelist() if cfg['member'] in n
                     and not n.endswith('.xml')), None)
        if not name:
            return
        with z.open(name) as raw:
            for line in io.TextIOWrapper(raw, encoding='utf-8', errors='replace'):
                line = line.strip()
                if line:
                    yield line


def iter_bible(cfg):
    path = cfg['path']
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    for book in data.get('books', []):
        for ch in book.get('chapters', []):
            for v in ch.get('verses', []):
                if isinstance(v, str) and v.strip():
                    yield v.strip()


def iter_local(cfg):
    root = cfg['path']
    if not os.path.isdir(root):
        return
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            if name.endswith('.gitkeep') or name.endswith('.json'):
                continue
            path = os.path.join(dirpath, name)
            opener = gzip.open if name.endswith('.gz') else open
            try:
                with opener(path, 'rt', encoding='utf-8', errors='replace') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            yield line
            except (OSError, UnicodeError):
                continue


def source_iter(name, cfg, cache):
    if cfg['kind'] == 'hf':
        return iter_hf(cfg)
    if cfg['kind'] == 'cc100':
        return iter_cc100(cfg, cache)
    if cfg['kind'] == 'opus':
        return iter_opus(cfg, cache)
    if cfg['kind'] == 'bible':
        return iter_bible(cfg)
    if cfg['kind'] == 'local':
        return iter_local(cfg)
    raise ValueError(f'unknown kind {cfg["kind"]}')


def load_tokenizer(name):
    if not name:
        return None
    try:
        from transformers import AutoTokenizer
        return AutoTokenizer.from_pretrained(name)
    except Exception as exc:
        log(f'  [warn] tokenizer unavailable ({exc}); estimating tokens')
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--out', default=os.path.expanduser('~/amharic-corpus'))
    ap.add_argument('--sources', default='wikipedia,cc100,opus_tatoeba,bible,local',
                    help='comma list; "all" for every source')
    ap.add_argument('--max-gb-per-source', type=float, default=8.0,
                    help='stop a source once its shards reach this size (0 = no cap)')
    ap.add_argument('--shard-docs', type=int, default=20000)
    ap.add_argument('--dedup-max', type=int, default=20_000_000,
                    help='exact-dedup hash table cap')
    ap.add_argument('--tokenizer', default='Qwen/Qwen2.5-1.5B-Instruct')
    ap.add_argument('--token-sample', type=int, default=1,
                    help='tokenize 1 in N docs and scale (faster; 1 = exact)')
    ap.add_argument('--force', action='store_true', help='re-ingest done sources')
    args = ap.parse_args()

    root = os.path.abspath(os.path.expanduser(args.out))
    cache = os.path.join(root, '_raw')
    os.makedirs(cache, exist_ok=True)
    manifest_path = os.path.join(root, 'manifest.json')
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding='utf-8') as f:
            manifest = json.load(f)

    tokenizer = load_tokenizer(args.tokenizer)
    if tokenizer is None:
        log('token counts will be approximate')

    names = list(SOURCES) if args.sources == 'all' else \
        [s.strip() for s in args.sources.split(',') if s.strip()]
    cap_bytes = int(args.max_gb_per_source * 1e9) if args.max_gb_per_source else 0

    for name in names:
        if name not in SOURCES:
            log(f'[warn] unknown source {name!r} — skipping')
            continue
        cfg = SOURCES[name]
        if not args.force and manifest.get(name, {}).get('done'):
            log(f'[skip] {name} already collected ({manifest[name]["docs"]} docs)')
            continue
        log(f'[ {name} ] licence: {cfg["license"]}')
        source_dir = os.path.join(root, name)
        if os.path.isdir(source_dir):
            shutil.rmtree(source_dir)
        writer = ShardWriter(root, name, args.shard_docs, tokenizer,
                             dedup=True, dedup_max=args.dedup_max,
                             token_sample=args.token_sample)
        kept = seen = 0
        stopped = ''
        try:
            for raw in source_iter(name, cfg, cache):
                seen += 1
                text = norm_text(raw)
                if not is_amharic(text, cfg.get('lang', 0.4)):
                    continue
                if writer.add(text):
                    kept += 1
                if cap_bytes and writer.docs and writer.bytes >= cap_bytes:
                    stopped = 'size-cap'
                    break
                if kept and kept % 200000 == 0:
                    log(f'    {name}: {kept:,} docs kept '
                        f'({writer.tokens:,} tokens, {writer.bytes/1e9:.1f} GB)')
        except KeyboardInterrupt:
            stopped = 'interrupted'
        except Exception as exc:
            stopped = f'error: {exc}'
            log(f'  [warn] {name}: {exc}')
        stats = writer.close()
        clean = stopped in ('', 'size-cap')
        if not clean and os.path.isdir(source_dir):
            shutil.rmtree(source_dir)
            stats['shards'] = []
            stats['docs'] = 0
            stats['tokens'] = 0
            stats['bytes'] = 0
        stats.update({'license': cfg['license'], 'url': cfg.get('url', cfg.get('zip', '')),
                      'seen': seen, 'kept': kept, 'stopped': stopped, 'done': clean})
        manifest[name] = stats
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        log(f'  ✓ {name}: {kept:,}/{seen:,} docs, {stats["tokens"]:,} tokens, '
            f'{stats["bytes"]/1e9:.2f} GB, {len(stats["shards"])} shard(s) {stopped}')

    total_docs = sum(v.get('docs', 0) for v in manifest.values())
    total_tokens = sum(v.get('tokens', 0) for v in manifest.values())
    total_bytes = sum(v.get('bytes', 0) for v in manifest.values())
    log(f'TOTAL: {total_docs:,} docs | ~{total_tokens/1e9:.2f}B tokens | '
        f'{total_bytes/1e9:.2f} GB compressed')
    log(f'manifest → {manifest_path}')


if __name__ == '__main__':
    main()
