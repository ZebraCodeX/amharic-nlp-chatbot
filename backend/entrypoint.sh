#!/usr/bin/env sh
# Run database migrations (SQLite lives on the persistent volume), then start.
set -e

python manage.py migrate --noinput

exec "$@"
