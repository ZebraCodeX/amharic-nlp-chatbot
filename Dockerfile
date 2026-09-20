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
    ZER_TTS=espeak \
    ZER_MODEL=/app/models/zer-qwen-q4_k_m.gguf

WORKDIR /app

# Optional: hosted GGUF for remote builds (Fly) where the 940 MB file is not
# in git. When it is bundled locally (models/) the build does not download.
ARG ZER_GGUF_URL=

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

# NOTE: External Hugging Face inference is used (LLM_BASE_URL + LLM_API_KEY).
# The embedded GGUF model is NOT bundled here to avoid OOM on constrained plans.
# If a local model is desired, set ZER_GGUF_URL at deploy time and uncomment
# the RUN block below.
#
# Embedded Zer model: bundled file wins; otherwise fetch from ZER_GGUF_URL.
# RUN python - <<'PY'
# import os, urllib.request
# dest = '/app/models/zer-qwen-q4_k_m.gguf'
# os.makedirs('/app/models', exist_ok=True)
# if os.path.exists(dest) and os.path.getsize(dest) > 10_000_000:
#     print('embedded model: bundled', os.path.getsize(dest) // (1024 * 1024), 'MB')
# elif os.environ.get('ZER_GGUF_URL'):
#     print('embedded model: downloading from ZER_GGUF_URL…')
#     urllib.request.urlretrieve(os.environ['ZER_GGUF_URL'], dest)
#     print('embedded model: downloaded', os.path.getsize(dest) // (1024 * 1024), 'MB')
# else:
#     print('embedded model: NOT bundled and no ZER_GGUF_URL — '
#           'the app will use the offline rule brain / remote LLM')
# PY

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
