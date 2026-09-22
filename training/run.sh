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
DATASET="${DATASET:-training/data/amharic_sft.clean.jsonl}"
EPOCHS="${EPOCHS:-3}"; BATCH="${BATCH:-4}"; GA="${GA:-4}"
LR="${LR:-2e-4}"; MAXLEN="${MAXLEN:-2048}"; VENV="${VENV:-.venv-train}"
# RESUME=1 continues from the latest checkpoint already in $OUT (safe to delete
# the line if you want a fresh run). EXTRA passes any other trainer flag.
RESUME_FLAG=""; [ "${RESUME:-0}" = "1" ] && RESUME_FLAG="--resume"

echo "▶ Zer QLoRA: model=$MODEL out=$OUT resume=${RESUME:-0}"

if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1090
. "$VENV/bin/activate"
pip install -q -U pip
pip install -q -r training/requirements-train.txt

# Some GPU base images (RunPod) set HF_HUB_ENABLE_HF_TRANSFER=1 without the
# package installed; drop it so model downloads don't hard-fail.
python -c "import hf_transfer" >/dev/null 2>&1 || unset HF_HUB_ENABLE_HF_TRANSFER

python training/build_dataset.py

python - <<'PY'
try:
    import torch
    if not torch.cuda.is_available():
        print("\n\033[33m⚠  No CUDA GPU detected. Training will be extremely slow on CPU.\033[0m\n")
except Exception:
    pass
PY

# Pull the free conversational/instruction corpora once, so the SFT set has
# ~270k real Amharic examples and not just the small seed set. Non-fatal.
if [ ! -f training/data/conversations_free.jsonl ] && [ "${SKIP_FETCH:-0}" != "1" ]; then
  echo "▶ Fetching free Amharic conversation corpora (one-time)…"
  python tools/fetch_conversation_corpus.py || \
    echo "  ⚠ fetch failed — continuing with the smaller seed set"
fi

# Sourced factual topics (Ethiopian history, Black American history, logic,
# free will, political power). Non-fatal if offline.
if [ ! -f training/data/topics_sft.jsonl ] && [ "${SKIP_FETCH:-0}" != "1" ]; then
  echo "▶ Fetching sourced factual topics…"
  python tools/fetch_topics.py || \
    echo "  ⚠ topic fetch failed — continuing without it"
fi

python training/build_dataset.py

# Compile the runtime topic KB, hold out a clean topic eval split, then filter
# degenerate/long/duplicate rows AND the held-out eval questions from training.
python tools/build_topic_kb.py || echo "  ⚠ topic KB build failed — skipping"
python training/build_eval.py || echo "  ⚠ eval split failed — skipping"
HOLDOUT_KEYS=training/data/topics_eval_keys.json
HOLDOUT_ARG=""
[ -f "$HOLDOUT_KEYS" ] && HOLDOUT_ARG="--holdout $HOLDOUT_KEYS"
python training/clean_dataset.py $HOLDOUT_ARG

python training/train_qlora.py \
  --model "$MODEL" --dataset "$DATASET" --out "$OUT" \
  --epochs "$EPOCHS" --batch "$BATCH" --grad-accum "$GA" \
  --lr "$LR" --max-len "$MAXLEN" $RESUME_FLAG ${EXTRA:-}

python training/merge_adapter.py --base "$MODEL" --adapter "$OUT" --out "${OUT}-merged" \
  ${MERGE_DEVICE:+--device "$MERGE_DEVICE"}

cat <<EOF

✅ Done. Merged model → ${OUT}-merged

Serve it OpenAI-compatibly and point the app at it:
  vllm serve ${OUT}-merged --port 8000 --served-model-name zer
  flyctl secrets set LLM_BASE_URL=https://YOUR-GPU-HOST/v1 LLM_MODEL=zer LLM_API_KEY=...

Sanity-check before serving:
  python training/eval.py --model ${OUT}-merged
EOF
