#!/usr/bin/env sh
# Run database migrations (SQLite lives on the persistent volume), then start.
# NOTE: keep the CWD at /app/backend — gunicorn resolves `config.wsgi` from it.
set -e

cd /app/backend

python manage.py migrate --noinput

# Preload the embedded Zer model so the first chat is instant on a fresh
# machine. Quietly skips when llama-cpp-python or the model file is missing.
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
