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
    ZER_TTS=espeak

WORKDIR /app

# espeak-ng: open-source TTS with Amharic support. ffmpeg: audio decoding.
RUN apt-get update \
    && apt-get install -y --no-install-recommends espeak-ng ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements-speech.txt /app/backend/
# Torch CPU-only (smaller than the default CUDA wheels) then the rest.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir \
        -r /app/backend/requirements.txt \
        -r /app/backend/requirements-speech.txt

# Application code (frontend sources are dropped after the copy).
COPY . /app

# React build from stage 1.
COPY --from=webbuild /app/backend/static/spa /app/backend/static/spa

RUN rm -rf /app/amharic_nlp/corpora /app/frontend /app/.git /app/.venv \
        /app/tests /app/tools /app/static /app/templates \
        /app/__pycache__ /app/backend/__pycache__ \
    && mkdir -p /app/userdata

WORKDIR /app/backend
RUN python manage.py collectstatic --noinput && chmod +x /app/backend/entrypoint.sh

EXPOSE 8000
CMD ["/app/backend/entrypoint.sh", "gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "1", "--threads", "8", \
     "--timeout", "240", "--access-logfile", "-"]
