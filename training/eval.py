#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick sanity check of a (base or merged) model on Zer prompts.

    python training/eval.py --model training/out/zer-lora-merged
    python training/eval.py --model Qwen/Qwen2.5-1.5B-Instruct   # baseline

Prints generations, the detected response language, and whether the reply
matches the prompt language (Zer's core bilingual guarantee).
"""
import argparse
import os
import re
import sys

# See train_qlora.py: tolerate base images that set HF_HUB_ENABLE_HF_TRANSFER
# without installing hf_transfer.
try:
    import hf_transfer  # noqa: F401
except ImportError:
    os.environ.pop('HF_HUB_ENABLE_HF_TRANSFER', None)

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ETH = re.compile(r'[\u1200-\u137f]')
LATIN = re.compile(r'[A-Za-z]')

PROMPTS = [
    'ጤና እንዴት እጠብቅ?',
    'ስለ ኢትዮጵያ ቡና ንገረኝ።',
    'ፓይቶን ኮድ ጻፍልኝ ድምር',
    'What is the capital of Ethiopia?',
    'Write a short poem about coffee in English.',
]


def lang_of(text):
    am, en = len(ETH.findall(text)), len(LATIN.findall(text))
    if am and am >= en:
        return 'am'
    return 'en' if en else '?'


def prompt_lang(p):
    return lang_of(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', required=True)
    ap.add_argument('--max-new-tokens', type=int, default=200)
    ap.add_argument('--limit', type=int, default=len(PROMPTS))
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32)
    model.eval()
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model.to(device)

    ok = 0.0
    for p in PROMPTS[:args.limit]:
        if getattr(tok, 'chat_template', None):
            text = tok.apply_chat_template([{'role': 'user', 'content': p}],
                                           tokenize=False, add_generation_prompt=True)
        else:
            text = f'### User\n{p}\n### Assistant\n'
        inputs = tok(text, return_tensors='pt').to(device)
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=args.max_new_tokens,
                                 do_sample=False, pad_token_id=tok.eos_token_id)
        reply = tok.decode(out[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True).strip()
        want = prompt_lang(p)
        got = lang_of(reply)
        ok += 1.0 if got == want else 0.0
        print('=' * 70)
        print('PROMPT :', p)
        print('REPLY  :', reply[:400].replace('\n', ' '))
        print(f'LANG   : want={want} got={got} {"✓" if got == want else "✗"}')
    print('=' * 70)
    n = min(args.limit, len(PROMPTS))
    print(f'language-match: {ok:.0f}/{n}')


if __name__ == '__main__':
    sys.exit(0)
