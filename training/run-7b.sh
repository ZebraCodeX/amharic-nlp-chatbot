#!/usr/bin/env bash
# 7B QLoRA wrapper around run.sh — best-quality Zer fine-tune on a 24 GB GPU
# (RTX 4090/3090, A10, L4, A100) or a long free-GPU session (Kaggle 2×T4).
#
#   bash training/run-7b.sh                 # train + merge, checkpoints every 200 steps
#   RESUME=1 bash training/run-7b.sh        # continue after an eviction / session cut
#   EPOCHS=1 bash training/run-7b.sh        # quick single pass
#   MERGE_DEVICE=cpu bash training/run-7b.sh  # merge on CPU (low VRAM)
#
# Everything is overridable: MODEL, OUT, DATASET, EPOCHS, BATCH, GA, LR, MAXLEN,
# EXTRA, MERGE_DEVICE. See training/run.sh for the full pipeline.
set -euo pipefail
cd "$(dirname "$0")/.."

export MODEL="${MODEL:-Qwen/Qwen2.5-7B-Instruct}"
export OUT="${OUT:-training/out/zer-qwen7b-lora}"
export EPOCHS="${EPOCHS:-2}"
export BATCH="${BATCH:-1}"
export GA="${GA:-16}"
export LR="${LR:-1e-4}"
export MAXLEN="${MAXLEN:-2048}"
# 7B wants the wider LoRA from configs/qwen2.5-7b-qlora.yaml, plus frequent
# checkpoints so a spot eviction (or a free-tier session cut) is recoverable.
export EXTRA="${EXTRA:---lora-r 32 --lora-alpha 64 --save-steps 200}"
if [ "${RESUME:-0}" = "1" ]; then
  export EXTRA="$EXTRA --resume"
fi

echo "▶ Zer 7B QLoRA: model=$MODEL batch=$BATCH ga=$GA maxlen=$MAXLEN out=$OUT"
exec bash training/run.sh
