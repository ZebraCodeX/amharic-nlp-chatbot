#!/usr/bin/env bash
# Point the deployed Zer app at your GPU host (no redeploy needed).
#
#   LLM_BASE_URL=https://xxxx.trycloudflare.com/v1 \
#   LLM_MODEL=zer LLM_API_KEY=… bash training/connect-fly.sh
#
# Re-run this whenever the tunnel URL changes (quick tunnels are ephemeral).
set -euo pipefail

: "${LLM_BASE_URL:?export LLM_BASE_URL=https://YOUR-URL/v1 first}"
: "${LLM_API_KEY:?export LLM_API_KEY=… first (the key from serve.sh)}"
LLM_MODEL="${LLM_MODEL:-zer}"
FLY_APP="${FLY_APP:-am-ai}"
export PATH="$HOME/.fly/bin:$PATH"

echo "▶ Setting secrets on Fly app '$FLY_APP' → $LLM_BASE_URL (model $LLM_MODEL)"
flyctl secrets set \
  LLM_BASE_URL="$LLM_BASE_URL" \
  LLM_MODEL="$LLM_MODEL" \
  LLM_API_KEY="$LLM_API_KEY" \
  --app "$FLY_APP"

echo "▶ Waiting for the app to pick up the new secrets…"
sleep 8

echo -n "llm-status: "
curl -s "https://$FLY_APP.fly.dev/api/llm-status" || true
echo
echo
echo "Try it:"
curl -s -X POST "https://$FLY_APP.fly.dev/api/chat/" \
  -H 'Content-Type: application/json' \
  -d '{"text":"ስለ ኮስሞስ አዲስ አረፍተ ነገር ጻፍልኝ"}' | head -c 400
echo
