#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_conversation_corpus.py — pull free *conversational* Amharic into corpora/.

The language model gets most of its "how people actually talk" signal from
dialogue. These are openly licensed, no-signup sources:

  addisgpt   AddisGPT-Amharic-Instruction — 796 real, human-verified user
             conversations (mostly Amharic), CC-BY-4.0
  finetome   addisai/FineTome-single-turn-dedup-amharic — 83k single-turn
             instruction conversations translated to Amharic
  tatoeba    Tatoeba Amharic everyday sentences, CC-BY-2.0-FR
  alpaca     iocuydi/amharic-alpaca — Alpaca translated to Amharic
  dolly      iocuydi/amharic-dolly-15k — Databricks Dolly translated
  ethionlp   EthioNLP/Amharic_Instruction_dataset — curated Amharic tasks
  gsm8k      simonbutt/amharic_gsm8k — Amharic grade-school math (CoT)

Everything lands as plain UTF-8 `.txt` under
`amharic_nlp/corpora/conversation/`, where the trainer picks it up.

Usage:
    python3 tools/fetch_conversation_corpus.py
    python3 tools/fetch_conversation_corpus.py --sources addisgpt,tatoeba
    python3 tools/fetch_conversation_corpus.py --limit 60000

Requires `pyarrow` for the parquet sources (use `.venv-train/bin/python`).
Pure stdlib for Tatoeba.
"""
import argparse
import ast
import functools
import io
import json
import os
import re
import sys
import tarfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'amharic_nlp', 'corpora', 'conversation')
# Downloaded parquet/tarballs are large; keep them out of a small /tmp. Override
# with --cache or $ZER_CORPUS_CACHE (e.g. on a data disk).
CACHE_DIR = os.environ.get('ZER_CORPUS_CACHE') or os.path.join(ROOT, '.hf-cache', 'corpus')

_UA = {'User-Agent': 'Zer-conversation-corpus/1.0'}

_PQ = 'https://huggingface.co/datasets/{}/resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet'

SOURCES = {
    'addisgpt': ('https://huggingface.co/datasets/AddisGPT/'
                 'AddisGPT-Amharic-Instruction/resolve/refs%2Fconvert%2Fparquet/'
                 'default/train/0000.parquet', 'addisgpt.parquet'),
    'finetome': ('https://huggingface.co/datasets/addisai/'
                 'FineTome-single-turn-dedup-amharic/resolve/refs%2Fconvert%2F'
                 'parquet/default/train/0000.parquet', 'finetome.parquet'),
    # Additional openly-licensed Amharic instruction sets (CC-BY / Apache-2.0).
    'alpaca': (_PQ.format('iocuydi/amharic-alpaca'), 'alpaca.parquet'),
    'dolly': (_PQ.format('iocuydi/amharic-dolly-15k'), 'dolly.parquet'),
    'ethionlp': (_PQ.format('EthioNLP/Amharic_Instruction_dataset'),
                 'ethionlp.parquet'),
    'gsm8k': (_PQ.format('simonbutt/amharic_gsm8k'), 'gsm8k.parquet'),
    # QA sets: reading-comprehension style (short, factual answers).
    'henok_qa': (_PQ.format('Henok/amharic-qa'), 'henok_qa.parquet'),
    'dagim_qa': (_PQ.format('dagim/amharic-qa'), 'dagim_qa.parquet'),
}

# source -> (user column, assistant column, optional context column). Used both
# to write plain-text dialogue lines and to emit instruction→answer SFT pairs.
INSTRUCTION_FIELDS = {
    'addisgpt': ('instruction', 'output', None),
    'alpaca': ('prompt', 'chosen', None),
    'dolly': ('instruction', 'response', 'context'),
    'ethionlp': ('instruction', 'output', 'input'),
    'gsm8k': ('am_question', 'am_answer', None),
    'henok_qa': ('inputs', 'targets', None),
    'dagim_qa': ('question', 'answer', 'context'),
}
TEXT_FIELDS = {k: (v[0], v[1]) for k, v in INSTRUCTION_FIELDS.items()}
TATOEBA = ('https://downloads.tatoeba.org/exports/per_language/amh/'
           'amh_sentences.tsv.bz2')

_ETHIOPIC = re.compile(r'[\u1200-\u137f]')
_GE_TAIL = re.compile(r'[^\u1200-\u137f\s.,!?;:()\'"\-–—…\u1361-\u1368]+')
_WS = re.compile(r'\s+')


def _download(url, dest):
    if os.path.exists(dest):
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f'  downloading {url.rsplit("/", 1)[-1]} …')
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, 'wb') as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return dest


def _clean(text):
    if not text:
        return ''
    text = text.replace('\u00a0', ' ')
    text = _WS.sub(' ', text).strip()
    return text


def _is_amharic(text):
    return len(_ETHIOPIC.findall(text)) >= 3


def _usable(text):
    """Reject markup-heavy / code-heavy / non-conversational lines."""
    if not _is_amharic(text):
        return False
    if any(ch in text for ch in '_[]{}<>|`\\'):
        return False
    if 'http' in text.lower():
        return False
    am = len(_ETHIOPIC.findall(text))
    if am < len(text) * 0.35:          # mostly Latin → skip
        return False
    return True


def _sentences(text, min_len=4, max_len=240):
    parts = re.split(r'(?<=[።፧!?፡.])\s+', text)
    out = []
    for p in parts:
        p = _clean(p)
        if min_len <= len(p) <= max_len and _usable(p):
            out.append(p)
    return out


def _write(name, lines):
    lines = list(dict.fromkeys(lines))          # de-dup, keep order
    path = os.path.join(OUT_DIR, name)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'  → {len(lines):>7d} lines  {path}')
    return len(lines)


def _parquet_rows(path):
    import pyarrow.parquet as pq
    for batch in pq.ParquetFile(path).iter_batches(batch_size=512):
        yield from batch.to_pylist()


def fetch_instruction(name, limit):
    """Plain-text dialogue lines for any INSTRUCTION_FIELDS parquet source."""
    url, fname = SOURCES[name]
    path = _download(url, os.path.join(CACHE_DIR, fname))
    user_f, asst_f, _ctx = INSTRUCTION_FIELDS[name]
    out = []
    for row in _parquet_rows(path):
        if name == 'addisgpt' and str(row.get('language', '')).lower() != 'amharic':
            continue
        for field in (user_f, asst_f):
            out += _sentences(_clean(row.get(field) or ''))
        if limit and len(out) >= limit:
            break
    return _write(f'{name}.txt', out[:limit] if limit else out)


def fetch_addisgpt(limit):
    return fetch_instruction('addisgpt', limit)


def fetch_finetome(limit):
    url, fname = SOURCES['finetome']
    path = _download(url, os.path.join(CACHE_DIR, fname))
    out = []
    for row in _parquet_rows(path):
        raw = row.get('conversations_amharic') or ''
        try:
            turns = ast.literal_eval(raw) if isinstance(raw, str) else raw
        except (ValueError, SyntaxError):
            continue
        if not isinstance(turns, list):
            continue
        for turn in turns:
            content = turn.get('content') if isinstance(turn, dict) else None
            if content:
                out += _sentences(_clean(content))
        if limit and len(out) >= limit:
            break
    return _write('finetome.txt', out[:limit] if limit else out)


def fetch_tatoeba(limit):
    path = _download(TATOEBA, os.path.join(CACHE_DIR, 'amh_sentences.tsv.bz2'))
    import bz2
    out = []
    with bz2.open(path, 'rt', encoding='utf-8') as f:
        for line in f:
            cols = line.rstrip('\n').split('\t')
            if len(cols) >= 3:
                out += _sentences(_clean(cols[2]))
    return _write('tatoeba.txt', out[:limit] if limit else out)


FETCHERS = {'addisgpt': fetch_addisgpt, 'finetome': fetch_finetome,
            'tatoeba': fetch_tatoeba}
for _name in ('alpaca', 'dolly', 'ethionlp', 'gsm8k', 'henok_qa', 'dagim_qa'):
    FETCHERS[_name] = functools.partial(fetch_instruction, _name)


# ---------------------------------------------------------------------------
# instruction/answer pairs → SFT jsonl for the GPU QLoRA fine-tune
# ---------------------------------------------------------------------------
SFT_SYSTEM = (
    "Your name is Zer (ዘር), an Ethiopian AI assistant; 'ዘር' means 'seed'. "
    "Answer in the SAME language the user used: Amharic → Amharic in Ge'ez "
    "script, English → English."
)


def _sft_example(user, assistant):
    user, assistant = _clean(user), _clean(assistant)
    if len(user) < 2 or len(assistant) < 4:
        return None
    if not (_ETHIOPIC.search(user) or _ETHIOPIC.search(assistant)):
        return None
    return {'messages': [
        {'role': 'system', 'content': SFT_SYSTEM},
        {'role': 'user', 'content': user},
        {'role': 'assistant', 'content': assistant},
    ]}


def _combined_user(user, context):
    user, context = _clean(user), _clean(context)
    if context and context.lower() not in user.lower():
        return f'{user}\n\n{context}'.strip()
    return user


def _add_sft_parquet(name, examples, limit):
    url, fname = SOURCES[name]
    path = _download(url, os.path.join(CACHE_DIR, fname))
    user_f, asst_f, ctx_f = INSTRUCTION_FIELDS[name]
    for row in _parquet_rows(path):
        if name == 'addisgpt' and str(row.get('language', '')).lower() != 'amharic':
            continue
        user = _combined_user(row.get(user_f) or '',
                              row.get(ctx_f) or '' if ctx_f else '')
        ex = _sft_example(user, row.get(asst_f) or '')
        if ex:
            examples.append(ex)
        if limit and len(examples) >= limit:
            return


def _add_sft_finetome(examples, limit):
    url, fname = SOURCES['finetome']
    path = _download(url, os.path.join(CACHE_DIR, fname))
    for row in _parquet_rows(path):
        raw = row.get('conversations_amharic') or ''
        try:
            turns = ast.literal_eval(raw) if isinstance(raw, str) else raw
        except (ValueError, SyntaxError):
            continue
        if not isinstance(turns, list):
            continue
        msgs = [{'role': 'system', 'content': SFT_SYSTEM}]
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            role = 'assistant' if turn.get('role') == 'assistant' else 'user'
            content = _clean(turn.get('content') or '')
            if content:
                msgs.append({'role': role, 'content': content})
        if len(msgs) >= 3:
            examples.append({'messages': msgs})
        if limit and len(examples) >= limit:
            return


SFT_SOURCES = ['addisgpt', 'finetome', 'alpaca', 'dolly', 'ethionlp', 'gsm8k',
               'henok_qa', 'dagim_qa']


def write_sft(out_path, limit=0, sources=None, max_per_source=0):
    """Emit instruction→answer pairs from every requested source as SFT jsonl."""
    sources = sources or SFT_SOURCES
    examples = []
    for name in sources:
        start = len(examples)
        try:
            if name == 'finetome':
                _add_sft_finetome(examples, limit)
            elif name in INSTRUCTION_FIELDS:
                _add_sft_parquet(name, examples, limit)
            else:
                continue
        except ImportError:
            print('  [warn] pyarrow is required for SFT export')
            return _write_sft(out_path, examples)
        except Exception as exc:                       # pragma: no cover
            print(f'  [warn] {name} SFT failed: {exc}')
            continue
        if max_per_source and len(examples) - start > max_per_source:
            del examples[start + max_per_source:]
        print(f'    + {len(examples) - start:>6d} from {name}')

    return _write_sft(out_path, examples)


def _write_sft(out_path, examples):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + '\n')
    print(f'  → {len(examples):>7d} SFT conversations  {out_path}')
    return len(examples)


def main():
    global OUT_DIR, CACHE_DIR
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--sources',
                    default='addisgpt,finetome,tatoeba,alpaca,dolly,ethionlp,'
                            'gsm8k,henok_qa,dagim_qa')
    ap.add_argument('--limit', type=int, default=0,
                    help='cap sentences per source (0 = no cap)')
    ap.add_argument('--out', default=OUT_DIR)
    ap.add_argument('--cache', default=CACHE_DIR,
                    help='where to keep downloaded parquet/tarballs '
                         '(default: .hf-cache/corpus; env $ZER_CORPUS_CACHE)')
    ap.add_argument('--sft', default=os.path.join(
        ROOT, 'training', 'data', 'conversations_free.jsonl'),
        help='also write instruction/answer pairs here for QLoRA fine-tuning')
    ap.add_argument('--max-per-source', type=int, default=0,
                    help='cap SFT examples kept per source (0 = no cap); use to '
                         'balance the mix so a free-GPU run fits its budget')
    args = ap.parse_args()

    OUT_DIR = args.out
    CACHE_DIR = args.cache
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    wanted = [s.strip() for s in args.sources.split(',') if s.strip()]
    for name in wanted:
        if name not in FETCHERS:
            print(f'[warn] unknown source {name!r} — skipping')
            continue
        print(f'[{name}]')
        try:
            FETCHERS[name](args.limit)
        except ImportError:
            print('  [warn] pyarrow is required for parquet sources — run with '
                  '.venv-train/bin/python')
        except Exception as exc:                       # pragma: no cover
            print(f'  [warn] {name} failed: {exc}')
    if args.sft and any(n in wanted for n in SFT_SOURCES):
        print('[sft]')
        try:
            write_sft(args.sft, limit=args.limit,
                      sources=[n for n in wanted if n in SFT_SOURCES],
                      max_per_source=args.max_per_source)
        except ImportError:
            print('  [warn] pyarrow is required for SFT export')
    print('\nNow retrain:  python3 -m amharic_nlp.training --per-domain 150000')


if __name__ == '__main__':
    main()
