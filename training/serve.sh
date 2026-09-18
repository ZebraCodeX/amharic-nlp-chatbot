#!/usr/bin/env bash
# Serve the merged Zer model as an OpenAI-compatible API with an API key, then
# open a public tunnel so the deployed Fly app can reach your laptop GPU.
#
#   LLM_API_KEY=$(openssl rand -hex 20) bash training/serve.sh training/out/zer-lora-merged
#
# Requirements: a CUDA GPU on Linux (or WSL2 on Windows) + vLLM.
#   pip install vllm
# The tunnel (cloudflared) is optional — any public URL works: ngrok, Tailscale
# Funnel, or a router port-forward.
set -euo pipefail

MODEL="${1:-${MODEL:-training/out/zer-lora-merged}}"
PORT="${PORT:-8000}"
SERVED="${SERVED:-zer}"
MAXLEN="${MAXLEN:-4096}"
KEY="${LLM_API_KEY:-}"
if [ -z "$KEY" ]; then
  KEY="$(python3 -c 'import secrets; print(secrets.token_hex(20))')"
fi

if [ -d "$MODEL" ] && [ ! -e "$MODEL/config.json" ]; then
  echo "⚠  '$MODEL' is a directory without config.json — train + merge first:"
  echo "   MODEL=Qwen/Qwen2.5-1.5B-Instruct bash training/run.sh"
fi

if ! command -v vllm >/dev/null 2>&1; then
  echo "▶ Installing vLLM (one-time, large download)…"
  pip install -q vllm
fi

echo "▶ Starting vLLM — model=$MODEL port=$PORT name=$SERVED ${VLLM_EXTRA:-}"
vllm serve "$MODEL" \
  --served-model-name "$SERVED" \
  --host 127.0.0.1 --port "$PORT" \
  --api-key "$KEY" \
  --max-model-len "$MAXLEN" ${VLLM_EXTRA:-} &
VLLM_PID=$!
trap 'kill "$VLLM_PID" 2>/dev/null || true' EXIT

echo "▶ Waiting for the model to load…"
ready=""
for _ in $(seq 1 180); do
  if curl -sf -H "Authorization: Bearer $KEY" \
       "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done

if [ -z "$ready" ]; then
  echo "✗ vLLM didn't come up — check the log above (VRAM / model path)."
  exit 1
fi

LOCAL_KEY_CMD="LLM_MODEL=$SERVED LLM_API_KEY=$KEY"
echo
echo "✓ Local endpoint ready:  http://127.0.0.1:$PORT/v1"
echo
echo "Next: in a SECOND terminal, run training/connect-fly.sh with a public URL."
echo

if command -v cloudflared >/dev/null 2>&1; then
  echo "▶ Opening a public tunnel (cloudflared). Copy the https://….trycloudflare.com"
  echo "  URL that appears below, then run:"
  echo
  echo "    LLM_BASE_URL=https://THAT-URL/v1 $LOCAL_KEY_CMD bash training/connect-fly.sh"
  echo
  cloudflared tunnel --url "http://127.0.0.1:$PORT"
else
  cat <<EOF
No cloudflared installed. Expose port $PORT with one of:
  • cloudflared tunnel --url http://127.0.0.1:$PORT     (free quick tunnel)
  • ngrok http $PORT
  • tailscale funnel $PORT
Then point the app at it:
  LLM_BASE_URL=https://YOUR-PUBLIC-URL/v1 $LOCAL_KEY_CMD bash training/connect-fly.sh
EOF
  wait "$VLLM_PID"
fi
