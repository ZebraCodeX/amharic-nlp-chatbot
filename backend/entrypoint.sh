#!/usr/bin/env sh
# Run database migrations, then start.
# NOTE: keep the CWD at /app/backend — gunicorn resolves `config.wsgi` from it.
set -e

cd /app/backend

python manage.py migrate --noinput

# If no model was baked in at build time, pull the GGUF from ZER_GGUF_URL at
# runtime (Render/Heroku-style deployments set it as a plain env var). The
# build-time download in the Dockerfile covers Fly.io-style build args.
echo "▶ ensuring embedded Zer model…"
python - <<'PY'
import os, sys
sys.path.insert(0, '/app')
import zer_model

if zer_model.file_available():
    print('embedded model: bundled', zer_model.model_file())
elif os.environ.get('ZER_GGUF_URL'):
    import urllib.request
    dest = zer_model.model_file()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print('embedded model: downloading from ZER_GGUF_URL…')
    try:
        urllib.request.urlretrieve(os.environ['ZER_GGUF_URL'], dest)
        print('embedded model: downloaded', os.path.getsize(dest) // (1024 * 1024), 'MB')
    except Exception as exc:
        print('embedded model: download failed:', exc)
else:
    print('embedded model: not bundled and no ZER_GGUF_URL — '
          'the app will use the offline rule brain / remote LLM')
PY

# Preload the embedded Zer model only when no external LLM is configured.
# When LLM_BASE_URL is set (e.g. Hugging Face inference), skip warm to avoid
# out-of-memory on constrained plans; the app will use the remote endpoint.
if [ -z "${LLM_BASE_URL:-}" ]; then
  echo "▶ warming embedded Zer model…"
  python - <<'PY' || echo "model warm skipped (offline fallback remains)"
import sys
sys.path.insert(0, '/app')
import zer_model
ok = zer_model.load()
print('embedded model warm:', 'ready' if ok else 'unavailable',
      '->', zer_model.status().get('model'))
PY
else
  echo "▶ external LLM configured (LLM_BASE_URL set) — skipping model warm"
fi

exec "$@"
