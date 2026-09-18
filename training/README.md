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

## Free GPU: Colab / Kaggle (in-policy)

Open **[`colab_zer_qlora.ipynb`](colab_zer_qlora.ipynb)** in Colab or Kaggle. It
clones the repo, installs the stack, builds the dataset, QLoRA-trains **Qwen2.5**
(1.5 B fits any T4; 3 B for better quality), merges the adapter, runs the eval,
and downloads `zer-lora.zip`. Kaggle saves your `/kaggle/working` outputs.

Respect the free tiers: one account, one session at a time — no parallel/multi-
account tricks to get more quota.

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/ZebraCodeX/amharic-nlp-chatbot/blob/main/training/colab_zer_qlora.ipynb)

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

## 4. Connect your own GPU laptop to the deployed app

Your laptop is behind a home router, so the Fly app can't reach it directly —
you open a tunnel. One command serves the model and opens it; one command points
the app at it. There is **no redeploy** and the offline brain stays as fallback.

### On the GPU laptop (Linux, or Windows via WSL2)

```bash
# one-time: CUDA build of torch + the training stack
python3 -m venv .venv-train && . .venv-train/bin/activate
pip install -r training/requirements-train.txt

# 1) build the dataset (fetch real conversations first, then the SFT set)
.venv-train/bin/python tools/fetch_conversation_corpus.py   # needs pyarrow
python training/build_dataset.py                            # ~84k conversations

# 2) fine-tune + merge  (pick the model by VRAM — see the table below)
MODEL=Qwen/Qwen2.5-1.5B-Instruct bash training/run.sh
python training/eval.py --model training/out/zer-lora-merged

# 3) serve it with an API key + a public tunnel
LLM_API_KEY=$(openssl rand -hex 20) bash training/serve.sh training/out/zer-lora-merged
#   → prints a https://….trycloudflare.com URL and the key
```

Then, in a second terminal (can be any machine with `flyctl`):

```bash
LLM_BASE_URL=https://THAT-URL/v1 LLM_MODEL=zer LLM_API_KEY=THE-KEY \
  bash training/connect-fly.sh          # or: make connect-llm
```

Verify: `curl https://am-ai.fly.dev/api/llm-status` → `{"available":true,…}` and
the header ✦ AI chip lights up. Ask an open question and it now **generates**.

### Which Qwen fits?

| GPU VRAM | Model | Notes |
| --- | --- | --- |
| 6–8 GB | `Qwen/Qwen2.5-1.5B-Instruct` | QLoRA fits; fast inference |
| 10–12 GB | `Qwen/Qwen2.5-3B-Instruct` | better Amharic, batch 1–2 |
| 16–24 GB | `Qwen/Qwen2.5-7B-Instruct` | best quality, `BATCH=2 GA=8` |

- **Windows:** run all of this inside **WSL2** (vLLM is Linux-only). Native
  Windows alternative: convert the merged model to GGUF with `llama.cpp`
  (`convert_hf_to_gguf.py`) and `ollama create zer -f Modelfile`; Ollama serves
  an OpenAI-compatible `/v1` too — use that URL with `connect-fly.sh`.
- **Quick tunnels change URL** on every restart — just re-run `connect-fly.sh`
  with the new URL. For a stable URL use a named Cloudflare tunnel or Tailscale
  Funnel.
- **Security:** the tunnel exposes your model. Always keep `LLM_API_KEY` set
  (vLLM enforces it) and stop `serve.sh` (Ctrl-C) when you're done.
- **Latency:** requests now go Fly → your laptop. Keep the laptop awake; expect
  a few seconds per answer on consumer GPUs.

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
