#!/usr/bin/env bash
# Serve a GGUF model with llama.cpp's OpenAI-compatible server, protected by an
# API key, with an optional public tunnel so the Fly app can reach the laptop.
#
#   LLM_API_KEY=$(openssl rand -hex 20) bash training/serve-llama.sh model.Q4_K_M.gguf
#
# Smaller/faster than vLLM on CPU/iGPU and gives an API key + /v1 endpoint, which
# is what a 16 GB laptop needs for a 14B model.
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${1:-${MODEL:-}}"
PORT="${PORT:-8000}"
CTX="${CTX:-4096}"
GPU_LAYERS="${GPU_LAYERS:-99}"     # offload everything to the GPU
LLAMA_DIR="${LLAMA_DIR:-training/llama.cpp}"
SERVED="${SERVED:-zer}"
KEY="${LLM_API_KEY:-}"
if [ -z "$KEY" ]; then
  KEY="$(python3 -c 'import secrets; print(secrets.token_hex(20))')"
fi

if [ -z "$MODEL" ] || [ ! -f "$MODEL" ]; then
  echo "✗ pass a .gguf file:  bash training/serve-llama.sh training/out/zer-lora-merged.Q4_K_M.gguf"
  exit 1
fi

BIN="$LLAMA_DIR/build/bin/llama-server"
if [ ! -x "$BIN" ]; then
  echo "▶ Building llama.cpp server…"
  [ -d "$LLAMA_DIR" ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp "$LLAMA_DIR"
  cmake -S "$LLAMA_DIR" -B "$LLAMA_DIR/build" -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release
  cmake --build "$LLAMA_DIR/build" --config Release -j "$(nproc)" --target llama-server
fi

echo "▶ llama-server on 127.0.0.1:$PORT (alias '$SERVED', ctx $CTX, ngl $GPU_LAYERS)"
"$BIN" -m "$MODEL" --host 127.0.0.1 --port "$PORT" \
  --api-key "$KEY" --alias "$SERVED" -ngl "$GPU_LAYERS" -c "$CTX" &
PID=$!
trap 'kill "$PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 90); do
  if curl -sf -H "Authorization: Bearer $KEY" \
       "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo
echo "✓ Local endpoint:  http://127.0.0.1:$PORT/v1    API key: $KEY"
echo

if command -v cloudflared >/dev/null 2>&1; then
  echo "▶ Opening a public tunnel. When the https://….trycloudflare.com URL appears, run:"
  echo
  echo "  LLM_BASE_URL=https://THAT-URL/v1 LLM_MODEL=$SERVED LLM_API_KEY=$KEY bash training/connect-fly.sh"
  echo
  cloudflared tunnel --url "http://127.0.0.1:$PORT"
else
  cat <<EOF
No cloudflared. Expose port $PORT with cloudflared/ngrok/tailscale, then:
  LLM_BASE_URL=https://YOUR-URL/v1 LLM_MODEL=$SERVED LLM_API_KEY=$KEY bash training/connect-fly.sh
EOF
  wait "$PID"
fi
