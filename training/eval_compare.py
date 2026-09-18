#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eval_compare.py — score one or more chat models on a held-out Amharic set.

Unlike eval.py (5 prompts, language match only), this computes real metrics per
model so fine-tunes can be compared fairly against the base model and other
open models you can load locally:

  * lang-match  — did the reply use the same language as the prompt (Zer's core
                  bilingual guarantee)? percent
  * rouge-l     — LCS F1 against the reference answer (macro mean), percent
  * chr-f       — character n-gram F-score (n=1..6, beta=2), percent
  * token-f1    — word-overlap F1 vs the reference (macro mean), percent
  * tok/s       — generation throughput

Usage:
    # one model
    python training/eval_compare.py --models Qwen/Qwen2.5-1.5B-Instruct \
        --test training/data/amharic_test.jsonl

    # fine-tune vs base, same test set and settings
    python training/eval_compare.py \
        --models training/out/zer-lora-merged,Qwen/Qwen2.5-1.5B-Instruct \
        --test training/data/amharic_test.jsonl --limit 200 --out results.json

Honesty note: this runs models it can load on *your* machine. It cannot compare
against closed frontier models (no local weights), so treat it as a transparent
same-hardware comparison, not a leaderboard of the world's best AI.
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter

try:
    import hf_transfer  # noqa: F401
except ImportError:
    os.environ.pop('HF_HUB_ENABLE_HF_TRANSFER', None)

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ETH = re.compile(r'[\u1200-\u137f]')
LATIN = re.compile(r'[A-Za-z]')
WS = re.compile(r'\s+')


def norm(text):
    text = (text or '').replace('\u00a0', ' ')
    return WS.sub(' ', text).strip()


def lang_of(text):
    am, en = len(ETH.findall(text)), len(LATIN.findall(text))
    if am and am >= en:
        return 'am'
    return 'en' if en else '?'


def lcs_len(a, b):
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            cur[j] = prev[j - 1] + 1 if ai == b[j - 1] else max(prev[j], cur[j - 1])
        prev = cur
    return prev[-1]


def rouge_l(hyp, ref):
    h, r = hyp.split(), ref.split()
    if not h or not r:
        return 0.0
    l = lcs_len(h, r)
    if l == 0:
        return 0.0
    p, rec = l / len(h), l / len(r)
    return 2 * p * rec / (p + rec)


def _ngrams(s, n):
    s = WS.sub('', s)
    return Counter(s[i:i + n] for i in range(len(s) - n + 1))


def chrf(hyp, ref, max_n=6, beta=2.0):
    total = 0.0
    b2 = beta * beta
    for n in range(1, max_n + 1):
        h, r = _ngrams(hyp, n), _ngrams(ref, n)
        if not h and not r:
            total += 1.0
            continue
        common = sum((h & r).values())
        p = common / max(1, sum(h.values()))
        rec = common / max(1, sum(r.values()))
        total += 0.0 if p + rec == 0 else (1 + b2) * p * rec / (b2 * p + rec)
    return total / max_n


def token_f1(hyp, ref):
    h, r = hyp.split(), ref.split()
    if not h or not r:
        return 0.0
    common = sum((Counter(h) & Counter(r)).values())
    if common == 0:
        return 0.0
    p, rec = common / len(h), common / len(r)
    return 2 * p * rec / (p + rec)


def build_prompt(tok, messages):
    if getattr(tok, 'chat_template', None):
        return tok.apply_chat_template(messages, tokenize=False,
                                       add_generation_prompt=True)
    head, user = messages[0], messages[1]
    return (f"### System\n{head['content']}\n### User\n{user['content']}\n"
            f"### Assistant\n")


def load_examples(path, limit):
    out = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            msgs = obj.get('messages') or []
            if len(msgs) >= 3:
                out.append({'prompt': msgs[:-1], 'reference': norm(msgs[-1]['content'])})
            if limit and len(out) >= limit:
                break
    return out


def evaluate(model_id, examples, args, device):
    tok = AutoTokenizer.from_pretrained(model_id)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    dtype = torch.float16 if device == 'cuda' else torch.float32
    model = AutoModelForCausalLM.from_pretrained(model_id, dtype=dtype)
    model.eval().to(device)

    agg = Counter()
    n = 0
    gen_tokens = 0
    started = time.time()
    samples = []
    for ex in examples:
        text = build_prompt(tok, ex['prompt'])
        ids = tok(text, add_special_tokens=False)['input_ids']
        if len(ids) > args.max_prompt_tokens:
            ids = ids[-args.max_prompt_tokens:]
        input_ids = torch.tensor([ids], device=device)
        inputs = {'input_ids': input_ids,
                  'attention_mask': torch.ones_like(input_ids)}
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=args.max_new_tokens,
                                 do_sample=False, pad_token_id=tok.eos_token_id)
        new_ids = out[0][input_ids.shape[1]:]
        reply = norm(tok.decode(new_ids, skip_special_tokens=True))
        gen_tokens += len(new_ids)
        want, got = lang_of(ex['prompt'][-1]['content']), lang_of(reply)
        agg['lang'] += 1.0 if got == want else 0.0
        agg['rouge'] += rouge_l(reply, ex['reference'])
        agg['chrf'] += chrf(reply, ex['reference'])
        agg['f1'] += token_f1(reply, ex['reference'])
        n += 1
        if args.progress and n % args.progress == 0:
            print(f'    {n}/{len(examples)} …', flush=True)
        if len(samples) < args.show:
            samples.append({'prompt': ex['prompt'][-1]['content'],
                            'reference': ex['reference'], 'reply': reply})

    elapsed = max(1e-6, time.time() - started)
    del model
    if device == 'cuda':
        torch.cuda.empty_cache()
    return {
        'model': model_id,
        'examples': n,
        'lang_match_%': round(100 * agg['lang'] / max(1, n), 1),
        'rouge_l_%': round(100 * agg['rouge'] / max(1, n), 1),
        'chr_f_%': round(100 * agg['chrf'] / max(1, n), 1),
        'token_f1_%': round(100 * agg['f1'] / max(1, n), 1),
        'gen_tok/s': round(gen_tokens / elapsed, 1),
        'seconds': round(elapsed, 1),
        'samples': samples,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--models', required=True,
                    help='comma-separated HF ids or local paths')
    ap.add_argument('--test', default='training/data/amharic_test.jsonl')
    ap.add_argument('--limit', type=int, default=200)
    ap.add_argument('--max-new-tokens', type=int, default=200)
    ap.add_argument('--max-prompt-tokens', type=int, default=1024,
                    help='left-truncate prompts to this many tokens (memory safety)')
    ap.add_argument('--show', type=int, default=1,
                    help='how many example generations to print per model')
    ap.add_argument('--progress', type=int, default=25,
                    help='print progress every N examples (0 = quiet)')
    ap.add_argument('--out', default='')
    args = ap.parse_args()

    if not os.path.exists(args.test):
        sys.exit(f'test file not found: {args.test}\n'
                 'Build it with the notebook split, or point --test at any SFT jsonl.')

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    examples = load_examples(args.test, args.limit)
    print(f'device={device}  examples={len(examples)}  test={args.test}\n')

    results = []
    for model_id in [m.strip() for m in args.models.split(',') if m.strip()]:
        print(f'▶ {model_id}')
        r = evaluate(model_id, examples, args, device)
        results.append(r)
        print(f"  lang-match {r['lang_match_%']}%  rouge-l {r['rouge_l_%']}%  "
              f"chr-f {r['chr_f_%']}%  token-f1 {r['token_f1_%']}%  "
              f"{r['gen_tok/s']} tok/s")
        for s in r['samples']:
            print(f"    Q: {s['prompt'][:120]}")
            print(f"    ref: {s['reference'][:160]}")
            print(f"    got: {s['reply'][:160]}")
        print()

    header = f"{'model':<52}{'lang%':>7}{'rougeL':>8}{'chrF':>7}{'tokF1':>7}{'tok/s':>8}"
    print(header)
    print('-' * len(header))
    for r in results:
        name = r['model'] if len(r['model']) <= 50 else '…' + r['model'][-49:]
        print(f"{name:<52}{r['lang_match_%']:>7}{r['rouge_l_%']:>8}"
              f"{r['chr_f_%']:>7}{r['token_f1_%']:>7}{r['gen_tok/s']:>8}")

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump([{k: v for k, v in r.items() if k != 'samples'} for r in results],
                      f, ensure_ascii=False, indent=2)
        print(f'\nsaved → {args.out}')


if __name__ == '__main__':
    main()
