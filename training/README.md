# Fine-tuning Zer (QLoRA)

This folder is a complete, in-policy pipeline for adapting an **open** base model
to Amharic and to Zer's behaviour. It builds the dataset from the data already in
this repo, QLoRA-fine-tunes, merges the adapter, and serves it back to the app.

> **Hardware reality.** QLoRA needs a **GPU** (the 4-bit path is CUDA-only) and
> roughly 8–24 GB of VRAM depending on model size. An SSD is storage, not
> compute. Do **not** split runs across free tiers to hide from a provider —
> that breaks their terms. Use GPUs you're allowed to consume.

## 1. Build the dataset (runs anywhere, no GPU)

```bash
python3 training/build_dataset.py
# → training/data/amharic_sft.jsonl  (517 seed examples from KB + rich answers
#   + dictionary + taught translations + Amharic codegen)
```

This is a **seed** set. For a model that generalises, mix in larger corpora
(respecting each licence): Amharic Wikipedia, CC-100 `am`, Masakhane/`am`
datasets, the EthioNLP collections, and your own `/review` corrections
(`data/user_translations.json` is picked up automatically).

## 2. Fine-tune

```bash
# GPU box (rented, your own, Kaggle/Colab within their rules, HF Jobs, …)
python3 -m venv .venv-train && . .venv-train/bin/activate
pip install -r training/requirements-train.txt

python training/train_qlora.py \
  --model Qwen/Qwen2.5-1.5B-Instruct \
  --dataset training/data/amharic_sft.jsonl \
  --out training/out/zer-qwen1.5b-lora \
  --epochs 3 --batch 4 --grad-accum 4 --lr 2e-4 --max-len 2048
```

CPU smoke test (proves the wiring, not quality):

```bash
python training/train_qlora.py --model sshleifer/tiny-gpt2 \
  --dataset training/data/amharic_sft.jsonl --out /tmp/zer-smoke \
  --epochs 1 --batch 1 --max-len 128 --max-steps 1 --no-4bit --device cpu
```

Multi-GPU (legitimate sharding via Accelerate):

```bash
accelerate config          # choose multi-GPU
accelerate launch --num_processes 4 training/train_qlora.py --model Qwen/Qwen2.5-1.5B-Instruct ...
```

## 3. Merge and serve

```bash
python training/merge_adapter.py --base Qwen/Qwen2.5-1.5B-Instruct \
  --adapter training/out/zer-qwen1.5b-lora --out training/out/zer-merged

# OpenAI-compatible server (vLLM) — then point the app at it:
vllm serve training/out/zer-merged --port 8000 --served-model-name zer
# on the Django side:
flyctl secrets set LLM_BASE_URL=https://your-gpu-host/v1 LLM_MODEL=zer LLM_API_KEY=…
```

Zer automatically prefers the LLM for creative/open questions and keeps the
offline brain (`codegen.py`, knowledge base, translation) for everything else —
so the app works with or without the model.

## Using the 1 TB SSD

Put the big stuff there (models, HF cache, checkpoints, dataset):

```bash
# make it writable by your user (needs sudo once)
sudo chown -R "$USER":"$USER" /run/media/zee/revenue-server
export ZER_TRAIN=/run/media/zee/revenue-server/zer-training
mkdir -p "$ZER_TRAIN"/{data,hf-cache,out,logs}
export HF_HOME="$ZER_TRAIN/hf-cache"          # all model downloads land here
cp training/data/amharic_sft.jsonl "$ZER_TRAIN/data/"
python training/train_qlora.py --model Qwen/Qwen2.5-1.5B-Instruct \
  --dataset "$ZER_TRAIN/data/amharic_sft.jsonl" --out "$ZER_TRAIN/out/zer-lora"
```

A 1.5 B model in 4-bit needs ~1.5 GB for weights and a few GB per checkpoint —
the SSD comfortably holds many runs, LoRA adapters, and merged models.
