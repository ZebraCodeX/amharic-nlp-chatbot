# ---------------------------------------------------------------------------
# ሕሳር — Django REST Framework API + React (Vite) SPA.
# Stage 1 builds the React app; stage 2 runs gunicorn serving both.
# ---------------------------------------------------------------------------
FROM node:22-slim AS webbuild
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && (npm ci --no-audit --no-fund || npm install --no-audit --no-fund)
COPY frontend/ ./frontend/
# Vite writes to ../backend/static/spa (see frontend/vite.config.ts)
RUN cd frontend && npm run build


FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_DEBUG=0 \
    DJANGO_ALLOWED_HOSTS=* \
    HISAR_USERDATA_DIR=/app/userdata \
    HF_HOME=/app/userdata/hf \
    XDG_CACHE_HOME=/app/userdata/cache \
    ZER_WHISPER_MODEL=base \
    ZER_TTS=auto \
    ZER_MODEL=/app/models/zer-qwen-q4_k_m.gguf \
    ZER_MODEL_EN=/app/models/qwen2.5-1.5b-instruct-q4_k_m.gguf

WORKDIR /app

# Optional: hosted GGUFs for remote builds (Fly) where the model files are not
# in git. The Amharic model is required; the English base model is fetched when
# a URL is given (default) and skipped otherwise.
ARG ZER_GGUF_URL=
ARG ZER_GGUF_EN_URL=https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf

# espeak-ng: open-source TTS with Amharic support. ffmpeg: audio decoding.
# build-essential + cmake let llama-cpp-python compile if no wheel matches.
# libpq-dev: PostgreSQL client library for psycopg2
RUN apt-get update \
    && apt-get install -y --no-install-recommends espeak-ng ffmpeg build-essential cmake libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements-speech.txt /app/backend/
# Torch CPU-only (smaller than the default CUDA wheels) then the rest.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir \
        -r /app/backend/requirements.txt \
        -r /app/backend/requirements-speech.txt \
    && pip install --no-cache-dir llama-cpp-python \
        --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

# Application code (frontend sources are dropped after the copy).
COPY . /app

# Embedded Zer models: the bundled files win; otherwise fetch them from the
# ZER_GGUF*_URL build args so the shipped image ALWAYS contains the trained
# Amharic model plus the coherent English base model. The runtime itself never
# calls an external inference endpoint.
RUN python - <<'PY'
import os, sys, urllib.request


def fetch(dest, env, required):
    if os.path.exists(dest) and os.path.getsize(dest) > 10_000_000:
        print('model: bundled', dest, os.path.getsize(dest) // (1024 * 1024), 'MB')
        return True
    url = os.environ.get(env)
    if not url:
        if required:
            sys.exit(f'model missing: bundle {dest} or set {env}')
        print('model: skipped (no %s)' % env)
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print('model: downloading %s → %s' % (env, dest))
    urllib.request.urlretrieve(url, dest)
    print('model: downloaded', dest, os.path.getsize(dest) // (1024 * 1024), 'MB')
    return True


fetch('/app/models/zer-qwen-q4_k_m.gguf', 'ZER_GGUF_URL', required=True)
fetch('/app/models/qwen2.5-1.5b-instruct-q4_k_m.gguf', 'ZER_GGUF_EN_URL', required=False)
PY

# React build from stage 1.
COPY --from=webbuild /app/backend/static/spa /app/backend/static/spa

RUN rm -rf /app/amharic_nlp/corpora /app/frontend /app/.git /app/.venv \
        /app/tests /app/tools /app/static /app/templates \
        /app/__pycache__ /app/backend/__pycache__ \
    && mkdir -p /app/userdata

WORKDIR /app/backend
RUN python manage.py collectstatic --noinput && chmod +x /app/backend/entrypoint.sh
EXPOSE 8080

CMD /app/backend/entrypoint.sh gunicorn config.wsgi:application \
     --bind 0.0.0.0:${PORT:-8080} \
     --workers 1 \
     --threads 8 \
     --timeout 240 \
     --access-logfile -
