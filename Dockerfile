# ሕሳር — pure-stdlib Amharic AI. No dependencies, so the image stays tiny.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    HOST=0.0.0.0 \
    HISAR_USERDATA_DIR=/app/userdata

WORKDIR /app

COPY . /app

# Drop build-only and bulk source corpora (the app only needs data/*.json).
RUN rm -rf /app/amharic_nlp/corpora /app/.git /app/__pycache__ \
        /app/**/__pycache__ /app/tests /app/tools \
    && mkdir -p /app/userdata

EXPOSE 8080

CMD ["python3", "chat_app.py"]
