"""Django settings for the ሕሳር backend.

The NLP brain (`chatbot.py`, `translator.py`, `llm.py`, `amharic_nlp/`) stays at
the repo root untouched; this Django project wraps it as a REST API. Configure
with environment variables so the same image runs in dev and on Fly.io.
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent        # backend/
REPO_ROOT = BASE_DIR.parent                              # repo root

# The legacy stdlib modules live at the repo root — make them importable.
for _p in (str(REPO_ROOT), str(BASE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def env_bool(name, default=False):
    return str(os.environ.get(name, default)).strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default=''):
    return [v.strip() for v in os.environ.get(name, default).split(',') if v.strip()]


SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-insecure-change-me')
DEBUG = env_bool('DJANGO_DEBUG', True)
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', '*')
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS', 'https://*.fly.dev')

INSTALLED_APPS = [
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'api',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {'context_processors': []},
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
SPA_DIR = BASE_DIR / 'static' / 'spa'          # Vite build lands here

STORAGES = {
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
    'UNAUTHENTICATED_USER': None,
}

# Voice clips are uploaded to /api/speech|voice. Keep well under Fly's limits.
MAX_AUDIO_BYTES = int(os.environ.get('MAX_AUDIO_BYTES', str(20 * 1024 * 1024)))
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_AUDIO_BYTES + (2 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000

# CORS: permissive in debug (Vite dev server on :5173), explicit in prod.
CORS_ALLOW_ALL_ORIGINS = env_bool('CORS_ALLOW_ALL', DEBUG)
CORS_ALLOWED_ORIGINS = env_list('CORS_ALLOWED_ORIGINS')
CORS_ALLOW_METHODS = ['GET', 'POST', 'OPTIONS']
CORS_ALLOW_HEADERS = ['content-type', 'accept']

# Behind Fly.io's proxy, trust the forwarded scheme.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', False)  # Fly handles TLS
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# Where the STL/JSON user data (corrections, memory) is written. Fly mounts a
# volume at /app/userdata via HISAR_USERDATA_DIR.
USER_DATA_DIR = Path(os.environ.get('HISAR_USERDATA_DIR', BASE_DIR / 'userdata'))
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('HISAR_USERDATA_DIR', str(USER_DATA_DIR))

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}
