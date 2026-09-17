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
    HISAR_USERDATA_DIR=/app/userdata

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Application code (frontend sources are dropped after the copy).
COPY . /app

# React build from stage 1.
COPY --from=webbuild /app/backend/static/spa /app/backend/static/spa

RUN rm -rf /app/amharic_nlp/corpora /app/frontend /app/.git /app/.venv \
        /app/tests /app/tools /app/static /app/templates \
        /app/__pycache__ /app/backend/__pycache__ \
    && mkdir -p /app/userdata

WORKDIR /app/backend
RUN python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "1", "--threads", "8", \
     "--timeout", "120", "--access-logfile", "-"]
