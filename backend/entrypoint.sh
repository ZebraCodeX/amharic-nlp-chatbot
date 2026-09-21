#!/usr/bin/env sh
# Run database migrations, then start.
# NOTE: keep the CWD at /app/backend — gunicorn resolves `config.wsgi` from it.
set -e

cd /app/backend

python manage.py migrate --noinput

# Confirm the trained Zer model is present. It is bundled into the image at
# build time (models/zer-qwen-q4_k_m.gguf); ZER_GGUF_URL is only a safety net
# for images that were built without it.
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
    print('embedded model: MISSING — the app will fall back to the rule brain')
PY

# Warm the trained model so the first chat request never pays the load.
# The embedded model is always preferred over any external endpoint, so we
# warm it unconditionally.
echo "▶ warming embedded Zer model…"
python - <<'PY' || echo "model warm skipped (offline fallback remains)"
import sys
sys.path.insert(0, '/app')
import zer_model
ok = zer_model.load()
print('embedded model warm:', 'ready' if ok else 'unavailable',
      '->', zer_model.status().get('model'))
PY

exec "$@"
