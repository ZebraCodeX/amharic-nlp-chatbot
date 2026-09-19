#!/usr/bin/env sh
# Run database migrations (SQLite lives on the persistent volume), then start.
set -e

python manage.py migrate --noinput

# Preload the embedded Zer model so the first chat is instant on a fresh
# machine. Quietly skips when llama-cpp-python or the model file is missing.
echo "▶ warming embedded Zer model…"
cd /app && python - <<'PY' || echo "model warm skipped (offline fallback remains)"
import sys
sys.path.insert(0, '/app')
import zer_model
ok = zer_model.load()
print('embedded model warm:', 'ready' if ok else 'unavailable',
      '->', zer_model.status().get('model'))
PY

exec "$@"
