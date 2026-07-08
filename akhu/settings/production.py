"""
AKHU AFIVS — Production Settings
PostgreSQL, Local Cache, Logging, HTTPS
"""
from .base import *
import dj_database_url
import os

DEBUG = False

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# PostgreSQL
DATABASES = {
    'default': dj_database_url.config(
        default=env('DATABASE_URL', default='postgresql://akhu:password@db:5432/akhu_verification'),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Local Cache (Redis disabled temporarily)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Sessions in Database
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# Security (Temporary disabled HTTPS flags until SSL works)
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Sentry
SENTRY_DSN = env('SENTRY_DSN', default='')
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

# Logging Setup
LOG_DIR = "/var/log/akhu"
os.makedirs(LOG_DIR, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.path.join(LOG_DIR, "django.log"),
            "maxBytes": 50 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
}
