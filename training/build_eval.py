#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_eval.py — carve a held-out evaluation set out of the compiled topic KB.

The topic knowledge (``data/knowledge_topics.json``) is also used for training,
so scoring on all of it would only measure memorisation. This splits it into:

  * ``training/data/topics_eval.jsonl``   — held out, never trained on
  * the rest                              — stays in the training set

and prints the keys so ``clean_dataset.py --holdout`` can drop the eval rows
from the training file. Format matches ``eval_compare.py`` (system/user/assistant
messages), so it can be passed straight to ``--test``.

    python3 training/build_eval.py                 # 30% held out
    python3 training/build_eval.py --frac 0.25 --seed 7
"""
import argparse
import json
import os
import random
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB = os.path.join(ROOT, 'data', 'knowledge_topics.json')
DEFAULT_OUT = os.path.join(ROOT, 'training', 'data', 'topics_eval.jsonl')

SYSTEM = (
    "Your name is Zer (ዘር), an Ethiopian AI assistant; 'ዘር' means 'seed'. "
    "Answer in the SAME language the user used: Amharic → Amharic in Ge'ez "
    "script, English → English."
)
_WS = re.compile(r'\s+')


def _key(text):
    return _WS.sub(' ', (text or '').lower()).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--kb', default=KB)
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--frac', type=float, default=0.30,
                    help='fraction of topics held out for evaluation')
    ap.add_argument('--seed', type=int, default=42)
    args = ap.parse_args()

    if not os.path.exists(args.kb):
        raise SystemExit(f'knowledge base not found: {args.kb} — '
                         'run tools/build_topic_kb.py')
    with open(args.kb, encoding='utf-8') as f:
        topics = json.load(f).get('topics', [])
    if not topics:
        raise SystemExit('no topics in the knowledge base')

    rows = sorted(topics, key=lambda t: t.get('id') or t.get('question') or '')
    random.Random(args.seed).shuffle(rows)
    n_eval = max(1, round(len(rows) * max(0.0, min(0.95, args.frac))))
    eval_rows, train_rows = rows[:n_eval], rows[n_eval:]

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        for t in eval_rows:
            f.write(json.dumps({'messages': [
                {'role': 'system', 'content': SYSTEM},
                {'role': 'user', 'content': t['question']},
                {'role': 'assistant', 'content': t['answer']},
            ]}, ensure_ascii=False) + '\n')

    keys_path = os.path.splitext(args.out)[0] + '_keys.json'
    with open(keys_path, 'w', encoding='utf-8') as f:
        json.dump(sorted({_key(t['question']) for t in eval_rows}),
                  f, ensure_ascii=False, indent=2)

    lang = {'am': sum(t['lang'] == 'am' for t in eval_rows),
            'en': sum(t['lang'] != 'am' for t in eval_rows)}
    print(f'→ held out {len(eval_rows)} / {len(rows)} topics ({lang}) → {args.out}')
    print(f'→ {len(train_rows)} topics stay in training; keys → {keys_path}')
    print(f'   next: python3 training/clean_dataset.py --holdout {keys_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
