#!/usr/bin/env bash
# Convert a merged HF model to a 4-bit GGUF for llama.cpp — this is how you run
# a 14B on a 16 GB laptop (Q4_K_M ≈ 9 GB, fits with room for context).
#
#   bash training/quantize_gguf.sh training/out/zer-lora-merged
#   → training/out/zer-lora-merged.Q4_K_M.gguf
#
# Needs: git, cmake, a C++ toolchain, python3. Builds llama.cpp once under
# training/llama.cpp (gitignored).
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${1:-training/out/zer-lora-merged}"
QUANT="${QUANT:-Q4_K_M}"
LLAMA_DIR="${LLAMA_DIR:-training/llama.cpp}"
OUT="${2:-${MODEL}.${QUANT}.gguf}"

if [ ! -d "$MODEL" ]; then
  echo "✗ merged model folder not found: $MODEL"
  exit 1
fi

if [ ! -d "$LLAMA_DIR" ]; then
  echo "▶ Cloning llama.cpp…"
  git clone --depth 1 https://github.com/ggml-org/llama.cpp "$LLAMA_DIR"
fi

if [ ! -x "$LLAMA_DIR/build/bin/llama-quantize" ]; then
  echo "▶ Building llama.cpp (needs cmake + a C++ compiler)…"
  cmake -S "$LLAMA_DIR" -B "$LLAMA_DIR/build" -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release
  cmake --build "$LLAMA_DIR/build" --config Release -j "$(nproc)" --target llama-quantize llama-cli
fi

echo "▶ Converting $MODEL → f16 GGUF…"
REQ="$LLAMA_DIR/requirements/requirements-convert_hf_to_gguf.txt"
if [ -f "$REQ" ]; then
  python3 -m pip install -q -r "$REQ" || true
fi
python3 "$LLAMA_DIR/convert_hf_to_gguf.py" "$MODEL" \
  --outfile "${OUT%.gguf}.f16.gguf" --outtype f16

echo "▶ Quantizing to $QUANT…"
"$LLAMA_DIR/build/bin/llama-quantize" "${OUT%.gguf}.f16.gguf" "$OUT" "$QUANT"

rm -f "${OUT%.gguf}.f16.gguf"
echo "✓ $OUT  ($(du -h "$OUT" | cut -f1))"
echo
echo "Serve it (with an API key + tunnel):"
echo "  LLM_API_KEY=\$(openssl rand -hex 20) bash training/serve-llama.sh $OUT"
