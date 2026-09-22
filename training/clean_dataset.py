#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean_dataset.py — filter and normalise a chat SFT jsonl before fine-tuning.

Raw crawled corpora (AddisGPT, FineTome, translated Alpaca/Dolly, EthioNLP,
GSM8K) contain noise that hurts a small model: control characters, 20k-char
runaway answers, degenerate repetition ("በድንገት በድንገት በድንገት …"), empty turns,
and exact duplicates. This pass removes them and writes a smaller, cleaner set.

    python3 training/clean_dataset.py \
        --in  training/data/amharic_sft.jsonl \
        --out training/data/amharic_sft.clean.jsonl \
        --report training/data/clean_report.json

Pure stdlib, so it runs on Kaggle/Colab without extra installs. Safe to re-run:
it never touches the input file.
"""
import argparse
import collections
import json
import os
import re
import sys

CONTROL = re.compile(r'[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f'
                     r'\u200b-\u200f\u202a-\u202e\u2060\ufeff]')
WS = re.compile(r'[ \t\u00a0]+')
MANY_NL = re.compile(r'\n{3,}')
ROLES = ('system', 'user', 'assistant')


def clean_text(text):
    if not isinstance(text, str):
        return ''
    text = CONTROL.sub('', text.replace('\r\n', '\n').replace('\r', '\n'))
    text = '\n'.join(WS.sub(' ', ln).strip() for ln in text.split('\n'))
    text = MANY_NL.sub('\n\n', text)
    return text.strip()


def degenerate(text):
    """True for runaway repetition or near-zero character diversity."""
    words = text.split()
    if len(words) >= 12:
        run = best = 1
        for i in range(1, len(words)):
            run = run + 1 if words[i] == words[i - 1] else 1
            best = max(best, run)
        if best >= 6:
            return True
    if len(text) >= 80 and len(set(text)) <= max(6, len(text) * 0.04):
        return True
    return False


def has_letters(text):
    return any(ch.isalpha() for ch in text)


def _key(text):
    return WS.sub(' ', (text or '').lower()).strip()


def _load_holdout(path):
    """Question keys to remove from training — from a keys JSON or eval jsonl."""
    if not path:
        return set()
    if not os.path.exists(path):
        sys.exit(f'holdout not found: {path}')
    keys = set()
    if path.endswith('.jsonl'):
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                for m in (json.loads(line).get('messages') or []):
                    if m.get('role') == 'user':
                        keys.add(_key(m.get('content')))
                        break
    else:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        for item in (data if isinstance(data, list) else []):
            keys.add(_key(item))
    return keys


def clean_example(obj, max_chars, min_answer, min_question):
    msgs = obj.get('messages')
    if not isinstance(msgs, list) or len(msgs) < 3:
        return None, 'structure'
    by_role = {}
    for m in msgs:
        if isinstance(m, dict) and m.get('role') in ROLES:
            by_role.setdefault(m['role'], m)
    user, answer = by_role.get('user'), by_role.get('assistant')
    if not user or not answer:
        return None, 'structure'
    system = by_role.get('system')

    user_t = clean_text(user.get('content'))
    ans_t = clean_text(answer.get('content'))
    sys_t = clean_text(system['content']) if system else None

    if len(user_t) < min_question:
        return None, 'question-short'
    if len(ans_t) < min_answer:
        return None, 'answer-short'
    if not has_letters(user_t) or not has_letters(ans_t):
        return None, 'no-letters'
    if len(ans_t) > max_chars or len(user_t) > max_chars:
        return None, 'too-long'
    if degenerate(ans_t):
        return None, 'degenerate'

    out = []
    if sys_t:
        out.append({'role': 'system', 'content': sys_t})
    out.append({'role': 'user', 'content': user_t})
    out.append({'role': 'assistant', 'content': ans_t})
    return {'messages': out}, None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--in', dest='src',
                    default='training/data/amharic_sft.jsonl')
    ap.add_argument('--out', dest='dst',
                    default='training/data/amharic_sft.clean.jsonl')
    ap.add_argument('--report', default='training/data/clean_report.json')
    ap.add_argument('--max-chars', type=int, default=6000,
                    help='drop an example if either turn exceeds this')
    ap.add_argument('--min-answer', type=int, default=4)
    ap.add_argument('--min-question', type=int, default=2)
    ap.add_argument('--holdout', default='',
                    help='eval jsonl or keys json (from training/build_eval.py) '
                         'whose questions are removed from training')
    ap.add_argument('--drop-system', action='store_true',
                    help='strip the system turn from every example')
    args = ap.parse_args()

    if not os.path.exists(args.src):
        sys.exit(f'input not found: {args.src}')
    holdout = _load_holdout(args.holdout)

    dropped = collections.Counter()
    seen = set()
    total = kept = 0

    os.makedirs(os.path.dirname(os.path.abspath(args.dst)), exist_ok=True)
    with open(args.src, encoding='utf-8') as fin, \
            open(args.dst, 'w', encoding='utf-8') as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                obj = json.loads(line)
            except ValueError:
                dropped['bad-json'] += 1
                continue

            ex, why = clean_example(obj, args.max_chars, args.min_answer,
                                    args.min_question)
            if ex is None:
                dropped[why] += 1
                continue

            if holdout:
                user = next((m['content'] for m in ex['messages']
                             if m['role'] == 'user'), '')
                if _key(user) in holdout:
                    dropped['holdout'] += 1
                    continue

            if args.drop_system:
                ex['messages'] = [m for m in ex['messages']
                                  if m['role'] != 'system']
                if len(ex['messages']) < 2:
                    dropped['structure'] += 1
                    continue

            key = '\x1f'.join(m['content'] for m in ex['messages']
                              if m['role'] != 'system').lower()
            if key in seen:
                dropped['duplicate'] += 1
                continue
            seen.add(key)

            fout.write(json.dumps(ex, ensure_ascii=False) + '\n')
            kept += 1
            if kept % 50000 == 0:
                print(f'  … {kept:,} kept', flush=True)

    report = {
        'input': args.src, 'output': args.dst,
        'total': total, 'kept': kept, 'dropped_total': total - kept,
        'dropped': dict(dropped.most_common()),
        'in_size_mb': round(os.path.getsize(args.src) / 1e6, 1),
        'out_size_mb': round(os.path.getsize(args.dst) / 1e6, 1),
    }
    with open(args.report, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f'\nkept {kept:,} / {total:,}  '
          f'({report["in_size_mb"]} MB → {report["out_size_mb"]} MB)')
    for reason, count in dropped.most_common():
        print(f'  dropped {count:>8,}  {reason}')
    print(f'report → {args.report}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
