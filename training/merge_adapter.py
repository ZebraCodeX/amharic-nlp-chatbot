#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge a trained LoRA adapter into the base model, ready to serve.

    python training/merge_adapter.py --base Qwen/Qwen2.5-1.5B-Instruct \
        --adapter training/out/zer-qwen-lora --out training/out/zer-merged
"""
import argparse

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--adapter', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.base)
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    base = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=dtype)
    model = PeftModel.from_pretrained(base, args.adapter)
    model = model.merge_and_unload()
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)
    print(f'merged model → {args.out}')


if __name__ == '__main__':
    main()
