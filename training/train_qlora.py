#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
train_qlora.py — QLoRA fine-tuning for Zer's Amharic dataset.

Fine-tunes an existing open model with 4-bit QLoRA (PEFT + bitsandbytes) on the
JSONL produced by build_dataset.py. On a GPU it uses nf4 4-bit; on CPU it falls
back to plain LoRA in float32 (slow — for a smoke test only).

Examples
--------
# GPU (24 GB), the real run:
python training/train_qlora.py --model Qwen/Qwen2.5-1.5B-Instruct \
    --dataset training/data/amharic_sft.jsonl --out training/out/zer-qwen-lora \
    --epochs 3 --batch 4 --grad-accum 4 --lr 2e-4

# CPU smoke test (validates the pipeline in ~a minute on a tiny model):
python training/train_qlora.py --model sshleifer/tiny-gpt2 \
    --dataset training/data/amharic_sft.jsonl --out /tmp/zer-smoke \
    --epochs 1 --batch 1 --max-len 128 --max-steps 1 --no-4bit --device cpu

Distributed (legitimately, across GPUs you may use) via Accelerate:
    accelerate launch --num_processes 4 training/train_qlora.py ...
"""
import argparse
import inspect
import json
import os

# Some GPU base images (e.g. RunPod's PyTorch) export HF_HUB_ENABLE_HF_TRANSFER=1
# without shipping the `hf_transfer` package — disable it rather than crash the
# download. (hf_transfer is in requirements-train.txt, so this is a safety net.)
try:
    import hf_transfer  # noqa: F401
except ImportError:
    os.environ.pop('HF_HUB_ENABLE_HF_TRANSFER', None)

import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainingArguments,
)

IGNORE = -100


def build_args():
    p = argparse.ArgumentParser()
    p.add_argument('--model', default='Qwen/Qwen2.5-1.5B-Instruct')
    p.add_argument('--dataset', default='training/data/amharic_sft.jsonl')
    p.add_argument('--out', default='training/out/zer-lora')
    p.add_argument('--epochs', type=float, default=3.0)
    p.add_argument('--batch', type=int, default=4)
    p.add_argument('--grad-accum', type=int, default=4)
    p.add_argument('--lr', type=float, default=2e-4)
    p.add_argument('--max-len', type=int, default=1024)
    p.add_argument('--lora-r', type=int, default=16)
    p.add_argument('--lora-alpha', type=int, default=32)
    p.add_argument('--lora-dropout', type=float, default=0.05)
    p.add_argument('--target-modules', default='auto')
    p.add_argument('--max-steps', type=int, default=-1)
    p.add_argument('--save-steps', type=int, default=0,
                   help='checkpoint every N steps (0 = per epoch). Use on spot GPUs.')
    p.add_argument('--resume', action='store_true',
                   help='resume from the latest checkpoint in --out (spot recovery)')
    p.add_argument('--no-4bit', action='store_true')
    p.add_argument('--device', default='auto', choices=['auto', 'cuda', 'cpu'])
    p.add_argument('--seed', type=int, default=42)
    return p.parse_args()


def pick_device(arg):
    if arg != 'auto':
        return arg
    return 'cuda' if torch.cuda.is_available() else 'cpu'


def chat_texts(messages, tokenizer):
    """Return (prompt_text, full_text) for one example."""
    if getattr(tokenizer, 'chat_template', None):
        full = tokenizer.apply_chat_template(messages, tokenize=False)
        prompt = tokenizer.apply_chat_template(messages[:-1], tokenize=False,
                                               add_generation_prompt=True)
        return prompt, full
    head, user, assistant = messages[0], messages[1], messages[-1]
    prompt = (f"### System\n{head['content']}\n### User\n{user['content']}\n"
              f"### Assistant\n")
    return prompt, prompt + assistant['content'] + (tokenizer.eos_token or '')


def main():
    args = build_args()
    device = pick_device(args.device)
    use_4bit = (device == 'cuda') and not args.no_4bit
    torch.manual_seed(args.seed)

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quant = None
    if use_4bit:
        from transformers import BitsAndBytesConfig
        quant = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type='nf4',
            bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True,
        )
    model = AutoModelForCausalLM.from_pretrained(
        args.model, quantization_config=quant,
        torch_dtype=torch.float16 if device == 'cuda' else torch.float32,
    )
    if use_4bit:
        model = prepare_model_for_kbit_training(model)
    model.config.use_cache = False

    targets = args.target_modules
    if targets == 'auto':
        names = {n.split('.')[-1] for n, _ in model.named_modules()}
        common = [t for t in ('q_proj', 'k_proj', 'v_proj', 'o_proj') if t in names]
        targets = common or 'all-linear'
    else:
        targets = [t.strip() for t in targets.split(',')]

    lora = LoraConfig(
        r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=args.lora_dropout,
        bias='none', task_type='CAUSAL_LM', target_modules=targets,
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    def tokenize(example):
        msgs = example['messages']
        prompt, full = chat_texts(msgs, tokenizer)
        p = tokenizer(prompt, add_special_tokens=False)['input_ids']
        f = tokenizer(full, add_special_tokens=False)['input_ids'][:args.max_len]
        labels = list(f)
        for i in range(min(len(p), len(labels))):
            labels[i] = IGNORE
        return {'input_ids': f, 'attention_mask': [1] * len(f), 'labels': labels}

    ds = load_dataset('json', data_files=args.dataset, split='train')
    ds = ds.map(tokenize, remove_columns=ds.column_names)

    collator = DataCollatorForSeq2Seq(tokenizer, model=model, padding=True,
                                      label_pad_token_id=IGNORE)
    # TrainingArguments changed across transformers versions — pass only what
    # this installed version accepts.
    wanted = {
        'output_dir': args.out, 'num_train_epochs': args.epochs,
        'per_device_train_batch_size': args.batch,
        'gradient_accumulation_steps': args.grad_accum,
        'learning_rate': args.lr, 'max_steps': args.max_steps,
        'logging_steps': 10, 'save_strategy': 'epoch', 'save_total_limit': 2,
        'fp16': (device == 'cuda'), 'report_to': [],
        'warmup_ratio': 0.03, 'lr_scheduler_type': 'cosine', 'seed': args.seed,
    }
    if args.save_steps > 0:
        wanted['save_strategy'] = 'steps'
        wanted['save_steps'] = args.save_steps
    accepted = set(inspect.signature(TrainingArguments.__init__).parameters)
    targs = TrainingArguments(**{k: v for k, v in wanted.items() if k in accepted})
    trainer = Trainer(model=model, args=targs, train_dataset=ds,
                      data_collator=collator)
    trainer.train(resume_from_checkpoint=args.resume or None)
    trainer.save_model(args.out)
    tokenizer.save_pretrained(args.out)
    with open(os.path.join(args.out, 'zer_train_meta.json'), 'w', encoding='utf-8') as f:
        json.dump(vars(args), f, ensure_ascii=False, indent=2)
    print(f'saved LoRA adapter → {args.out}')


if __name__ == '__main__':
    main()
