#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge a trained LoRA adapter into the base model, ready to serve.

    python training/merge_adapter.py --base Qwen/Qwen2.5-1.5B-Instruct \
        --adapter training/out/zer-qwen-lora --out training/out/zer-merged
"""
import argparse
import os

# See train_qlora.py: tolerate base images that set HF_HUB_ENABLE_HF_TRANSFER
# without installing hf_transfer.
try:
    import hf_transfer  # noqa: F401
except ImportError:
    os.environ.pop('HF_HUB_ENABLE_HF_TRANSFER', None)

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--adapter', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--device', default='auto', choices=['auto', 'cuda', 'cpu'],
                    help='merge on CPU if the GPU is too small for the full model')
    args = ap.parse_args()

    device = args.device
    if device == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'cpu'

    tokenizer = AutoTokenizer.from_pretrained(args.base)
    # fp16 halves memory; on CPU this avoids needing ~28 GB RAM for a 7B model.
    dtype = torch.float16
    base = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=dtype)
    model = PeftModel.from_pretrained(base, args.adapter)
    model = model.merge_and_unload()
    model.to(device)
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)
    print(f'merged model → {args.out} (device={device})')


if __name__ == '__main__':
    main()
