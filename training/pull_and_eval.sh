#!/usr/bin/env bash
# Pull a LoRA adapter from the Hugging Face Hub, merge it with the base model,
# and score it head-to-head against the base on the held-out Amharic test set.
#
#   REPO=your-name/zer-qwen-lora BASE=Qwen/Qwen2.5-1.5B-Instruct \
#     bash training/pull_and_eval.sh
#
# Needs HF_TOKEN in the environment (a read token is enough for a public repo;
# a private repo needs your own token with read access).
set -euo pipefail
cd "$(dirname "$0")/.."

VENV="${VENV:-.venv-train}"
REPO="${REPO:?set REPO=your-name/zer-lora}"
BASE="${BASE:-Qwen/Qwen2.5-1.5B-Instruct}"
OUT="${OUT:-training/out/pulled-lora}"
TEST="${TEST:-training/data/amharic_test.jsonl}"
LIMIT="${LIMIT:-100}"

PY="$VENV/bin/python"
[ -x "$PY" ] || PY=python3

echo "▶ pulling $REPO → $OUT"
"$PY" - "$REPO" "$OUT" <<'PY'
import sys
from huggingface_hub import snapshot_download
repo, out = sys.argv[1], sys.argv[2]
path = snapshot_download(repo_id=repo, local_dir=out)
print('downloaded →', path)
PY

if [ ! -f "$TEST" ]; then
  echo "▶ building held-out test set ($TEST)"
  "$PY" - "$TEST" <<'PY'
import random, sys
rows = [l for l in open('training/data/amharic_sft.jsonl', encoding='utf-8') if l.strip()]
random.Random(42).shuffle(rows)
open(sys.argv[1], 'w', encoding='utf-8').writelines(rows[:400])
print('wrote', sys.argv[1])
PY
fi

echo "▶ merging adapter into $BASE → $OUT-merged"
"$PY" training/merge_adapter.py --base "$BASE" --adapter "$OUT" --out "$OUT-merged"

echo "▶ scoring fine-tune vs base on $TEST"
"$PY" training/eval_compare.py \
  --models "$OUT-merged,$BASE" --test "$TEST" \
  --limit "$LIMIT" --max-new-tokens 128 --max-prompt-tokens 1024 \
  --show 1 --progress 10 --out "$OUT-eval.json"

echo "✓ results → $OUT-eval.json"
