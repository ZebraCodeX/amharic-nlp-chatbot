#!/usr/bin/env bash
# One-command QLoRA fine-tune + merge for Zer.
#
#   MODEL=Qwen/Qwen2.5-1.5B-Instruct bash training/run.sh
#   MODEL=Qwen/Qwen2.5-7B-Instruct BATCH=2 GA=8 MAXLEN=2048 bash training/run.sh
#
# Run this on a GPU machine you're allowed to use (own/rented/HF Jobs/Kaggle or
# Colab within their rules). It is NOT safe to split jobs to evade a provider.
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${MODEL:-Qwen/Qwen2.5-1.5B-Instruct}"
OUT="${OUT:-training/out/zer-lora}"
DATASET="${DATASET:-training/data/amharic_sft.jsonl}"
EPOCHS="${EPOCHS:-3}"; BATCH="${BATCH:-4}"; GA="${GA:-4}"
LR="${LR:-2e-4}"; MAXLEN="${MAXLEN:-2048}"; VENV="${VENV:-.venv-train}"

echo "▶ Zer QLoRA: model=$MODEL out=$OUT"

if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1090
. "$VENV/bin/activate"
pip install -q -U pip
pip install -q -r training/requirements-train.txt

python training/build_dataset.py

python - <<'PY'
try:
    import torch
    if not torch.cuda.is_available():
        print("\n\033[33m⚠  No CUDA GPU detected. Training will be extremely slow on CPU.\033[0m\n")
except Exception:
    pass
PY

python training/train_qlora.py \
  --model "$MODEL" --dataset "$DATASET" --out "$OUT" \
  --epochs "$EPOCHS" --batch "$BATCH" --grad-accum "$GA" \
  --lr "$LR" --max-len "$MAXLEN"

python training/merge_adapter.py --base "$MODEL" --adapter "$OUT" --out "${OUT}-merged"

cat <<EOF

✅ Done. Merged model → ${OUT}-merged

Serve it OpenAI-compatibly and point the app at it:
  vllm serve ${OUT}-merged --port 8000 --served-model-name zer
  flyctl secrets set LLM_BASE_URL=https://YOUR-GPU-HOST/v1 LLM_MODEL=zer LLM_API_KEY=...

Sanity-check before serving:
  python training/eval.py --model ${OUT}-merged
EOF
