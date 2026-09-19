#!/usr/bin/env bash
# Run the ሕሳር app (Zer).
#
# By default the app runs with the EMBEDDED model — the fine-tuned Zer
# Qwen2.5-1.5B GGUF (models/zer-qwen-q4_k_m.gguf) loaded in-process through
# llama.cpp: self-contained, no network, no API key. The offline brain stays as
# fallback if the model file or llama-cpp-python is missing.
#
# If the GGUF is NOT present locally, we point at the GPU-box endpoint instead
# (the fine-tuned model served by training/serve_hf.py on the LAN). Override:
#   ZER_GGUF=path/to/model.gguf   explicit file
#   ZER_LLM_URL=…                 skip embedded, use a remote endpoint
set -euo pipefail
cd "$(dirname "$0")"

GGUF="${ZER_GGUF:-models/zer-qwen-q4_k_m.gguf}"

if [ -n "${ZER_LLM_URL:-}" ]; then
  export LLM_BASE_URL="$ZER_LLM_URL"
  export LLM_API_KEY="${ZER_LLM_KEY:-}"
  export LLM_MODEL="${ZER_LLM_MODEL:-zer}"
  echo "▶ Zer LLM → $LLM_BASE_URL (model $LLM_MODEL)"
  exec python3 chat_app.py
fi

if [ -f "$GGUF" ]; then
  export ZER_MODEL="$(pwd)/$GGUF"
  echo "▶ Zer → embedded model: $GGUF (in-process, no network)"
  exec python3 chat_app.py
fi

echo "▶ no embedded model found ($GGUF) — using GPU box"
export LLM_BASE_URL="${ZER_LLM_URL:-http://192.168.1.160:8010/v1}"
export LLM_API_KEY="${ZER_LLM_KEY:-c0fe6a217d9fc36865e1725b681646e45c3b80c3}"
export LLM_MODEL="${ZER_LLM_MODEL:-zer}"
exec python3 chat_app.py