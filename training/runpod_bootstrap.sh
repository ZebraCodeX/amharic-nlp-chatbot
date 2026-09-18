#!/usr/bin/env bash
# runpod_bootstrap.sh — one-shot full training run ON a RunPod GPU pod.
#
# Launched by .github/workflows/train-runpod.yml, but you can also paste it into
# any pod's Web Terminal:
#
#   HF_TOKEN=hf_xxx HF_REPO=yourname/zer-qwen14b-lora \
#     MODEL=Qwen/Qwen2.5-14B-Instruct bash runpod_bootstrap.sh
#
# It: clones the repo → installs the stack → builds the ~84k conversation set →
# QLoRA-trains → merges → pushes the adapter to YOUR Hugging Face repo →
# writes a DONE marker → optionally terminates the pod (so it can't run away).
#
# All configuration is via environment variables (the workflow/pod passes them):
#   MODEL, EPOCHS, BATCH, GA, MAXLEN, OUT, EXTRA
#   HF_REPO (required to persist), HF_TOKEN (required to persist)
#   PUSH_MERGED=1 (optional, ~28 GB upload)
#   RUNPOD_API_KEY + SELF_TERMINATE=1 (pod deletes itself when finished)
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/ZebraCodeX/amharic-nlp-chatbot.git}"
MODEL="${MODEL:-Qwen/Qwen2.5-14B-Instruct}"
NEED_GB="${NEED_GB:-60}"   # 14B ≈ 28 GB base + 28 GB merged + dataset/slack
OUT="${OUT:-}"
EPOCHS="${EPOCHS:-2}"
BATCH="${BATCH:-1}"
GA="${GA:-16}"
MAXLEN="${MAXLEN:-2048}"
EXTRA="${EXTRA:---save-steps 200}"
HF_REPO="${HF_REPO:-}"
HF_TOKEN="${HF_TOKEN:-}"
PUSH_MERGED="${PUSH_MERGED:-0}"
SELF_TERMINATE="${SELF_TERMINATE:-1}"

log() { printf '\n[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }

trap 'log "✗ FAILED (line $LINENO)"; exit 1' ERR

log "RunPod training: model=$MODEL out=$OUT epochs=$EPOCHS"
nvidia-smi || true

# --- system deps (RunPod PyTorch images have CUDA + torch already) ----------
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -y >/dev/null 2>&1 || true
  apt-get install -y --no-install-recommends git python3-venv python3-pip >/dev/null 2>&1 || true
fi

# --- disk: use the biggest writable filesystem; fail FAST if it's too small ---
# (a half-downloaded 14B that dies on ENOSPC wastes GPU money — check up front)
pick_base() {
  local best="" best_avail=-1 d avail
  for d in /workspace /root /tmp /; do
    [ -d "$d" ] || continue
    avail=$(df -Pk "$d" 2>/dev/null | awk 'NR==2{print $4}')
    [ -n "$avail" ] || continue
    if [ "$avail" -gt "$best_avail" ]; then best_avail=$avail; best=$d; fi
  done
  printf '%s' "$best"
}
BASE_DIR="${ZER_BASE_DIR:-$(pick_base)}"
[ -n "$BASE_DIR" ] || BASE_DIR="/workspace"
WORKDIR="${WORKDIR:-$BASE_DIR/zer-run}"
free_gb=$(( $(df -Pk "$BASE_DIR" | awk 'NR==2{print $4}') / 1024 / 1024 ))
export HF_HOME="${ZER_HF_HOME:-$WORKDIR/hf-cache}"
OUT="${OUT:-$WORKDIR/zer-training/out/zer-lora}"

log "disk: base=$BASE_DIR (${free_gb} GiB free) — need ~${NEED_GB} GiB for $MODEL"
df -h "$BASE_DIR" 2>/dev/null || true
if [ "$free_gb" -lt "$NEED_GB" ]; then
  cat >&2 <<EOF
✗ Not enough disk: ${free_gb} GiB free on $BASE_DIR, need ~${NEED_GB} GiB.
  Recreate the pod with a bigger CONTAINER DISK (e.g. 200 GB) or attach a large
  volume, then rerun.  For a smaller model set MODEL and a lower NEED_GB.
EOF
  exit 1
fi
mkdir -p "$WORKDIR/zer-training/out" "$HF_HOME"

# --- code -------------------------------------------------------------------
cd "$WORKDIR"
if [ -d amharic-nlp-chatbot/.git ]; then
  git -C amharic-nlp-chatbot pull --ff-only || true
else
  git clone "$REPO_URL" amharic-nlp-chatbot
fi
cd amharic-nlp-chatbot

# --- python env -------------------------------------------------------------
if [ ! -d .venv-train ]; then python3 -m venv .venv-train; fi
# shellcheck disable=SC1091
. .venv-train/bin/activate
pip install -q -U pip
pip install -q -r training/requirements-train.txt

# RunPod's PyTorch image sets HF_HUB_ENABLE_HF_TRANSFER=1. Since hf_transfer is
# in requirements it should be present; if not, drop the flag so downloads work.
python -c "import hf_transfer" >/dev/null 2>&1 || unset HF_HUB_ENABLE_HF_TRANSFER

# --- dataset + train + merge (run.sh fetches conversations, builds SFT) -----
log "Building dataset + training (this is the long part)…"
MODEL="$MODEL" OUT="$OUT" EPOCHS="$EPOCHS" BATCH="$BATCH" GA="$GA" \
  MAXLEN="$MAXLEN" EXTRA="$EXTRA" bash training/run.sh

# --- persist to the Hugging Face Hub under YOUR account ---------------------
if [ -n "$HF_REPO" ] && [ -n "$HF_TOKEN" ]; then
  log "Pushing adapter → https://huggingface.co/$HF_REPO (private)"
  HF_TOKEN="$HF_TOKEN" python training/push_adapter.py --folder "$OUT" --repo "$HF_REPO"
  if [ "$PUSH_MERGED" = "1" ]; then
    HF_TOKEN="$HF_TOKEN" python training/push_adapter.py \
      --folder "${OUT}-merged" --repo "${HF_REPO}-merged"
  fi
else
  log "⚠ HF_REPO/HF_TOKEN not set — the model will be LOST when this pod ends."
fi

mkdir -p "$WORKDIR/zer-training"
{
  echo "status=complete"
  echo "model=$MODEL"
  echo "adapter=$OUT"
  echo "hf_repo=$HF_REPO"
  echo "finished=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} | tee "$WORKDIR/zer-training/DONE"
log "✓ TRAINING COMPLETE"

# --- self-terminate (never leave a GPU billing by accident) -----------------
if [ "$SELF_TERMINATE" = "1" ] && [ -n "${RUNPOD_API_KEY:-}" ] && [ -n "${RUNPOD_POD_ID:-}" ]; then
  log "Terminating pod $RUNPOD_POD_ID…"
  curl -sS --max-time 30 -X POST "https://api.runpod.io/graphql?api_key=${RUNPOD_API_KEY}" \
    -H 'Content-Type: application/json' \
    -d "{\"query\":\"mutation(\$i:PodTerminateInput!){podTerminate(input:\$i)}\",\"variables\":{\"i\":{\"podId\":\"${RUNPOD_POD_ID}\"}}}" \
    || true
fi
