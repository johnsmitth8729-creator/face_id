"""
AKHU Face Identity Verification System
Django Base Settings
"""
import os
from pathlib import Path
import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Read environment variables
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ['localhost', '127.0.0.1']),
    AI_ENGINE_MODE=(str, 'mock'),
    FACE_MATCH_THRESHOLD_VERIFIED=(float, 0.90),
    FACE_MATCH_THRESHOLD_REVIEW=(float, 0.80),
    HEAD_YAW_LEFT=(float, -12.0),
    HEAD_YAW_RIGHT=(float, 12.0),
    HEAD_PITCH_UP=(float, 10.0),
    CHALLENGE_COUNT=(int, 3),
    FACE_MATCH_WEIGHTS=(str, 'straight:0.5,left:0.2,right:0.2,up:0.1'),
    LIVENESS_BLINK_THRESHOLD=(float, 0.25),
    LIVENESS_CHALLENGE_TIMEOUT=(int, 30),
    LIVENESS_MAX_RETRIES=(int, 3),
    QR_TOKEN_EXPIRY_DAYS=(int, 365),
    USE_S3=(bool, False),
    SECURE_SSL_REDIRECT=(bool, False),
    SESSION_COOKIE_SECURE=(bool, False),
    CSRF_COOKIE_SECURE=(bool, False),
)

# Read .env file if it exists
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# SECRET KEY
SECRET_KEY = env('SECRET_KEY', default='django-insecure-development-key-change-in-production')

# ADMIN Credentials (from env, not DB)
ADMIN_USERNAME = env('ADMIN_USERNAME', default='admin')
ADMIN_PASSWORD = env('ADMIN_PASSWORD', default='Admin@AKHU2026!')
ADMIN_EMAIL = env('ADMIN_EMAIL', default='admin@akhu.uz')

# Outgoing email is intentionally disabled for this project.
EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'

# INSTALLED APPS
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    # Third-party
    'rest_framework',
    'corsheaders',
    'crispy_forms',
    'crispy_bootstrap5',

    # AFIVS Apps
    'apps.accounts',
    'apps.verification',
    'apps.liveness',
    'apps.face_engine',
    'apps.qr_module',
    'apps.supervisor',
    'apps.admin_panel',
    'apps.reports',
    'apps.audit',
]

# MIDDLEWARE
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.audit.middleware.AuditLogMiddleware',
    'apps.verification.middleware.CustomDebugErrorMiddleware',
]

ROOT_URLCONF = 'akhu.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
                'apps.accounts.context_processors.site_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'akhu.wsgi.application'
ASGI_APPLICATION = 'akhu.asgi.application'

# AUTH
AUTH_USER_MODEL = 'accounts.CustomUser'

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
]

# INTERNATIONALIZATION
LANGUAGE_CODE = 'en'
TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_L10N = True
USE_TZ = True

from django.utils.translation import gettext_lazy as _

LANGUAGES = [
    ('en', _('English')),
    ('uz', _('Uzbek')),
]

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

# STATIC FILES
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# MEDIA FILES
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# DEFAULT AUTO FIELD
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CRISPY FORMS
CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

# REST FRAMEWORK
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/hour',
        'user': '1000/hour',
        'verification': '10/hour',
    },
}

# CORS
CORS_ALLOWED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'https://faceid.akhu.uz',
    'https://verification.akhu.uz',
]

# SESSION
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_COOKIE_HTTPONLY = True
SESSION_SAVE_EVERY_REQUEST = True

# SECURITY
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True

# AI ENGINE SETTINGS
AI_ENGINE = {
    'MODE': env('AI_ENGINE_MODE', default='mock'),
    'THRESHOLD_VERIFIED': env('FACE_MATCH_THRESHOLD_VERIFIED'),
    'THRESHOLD_REVIEW': env('FACE_MATCH_THRESHOLD_REVIEW'),
    'MODEL_PACK': env('INSIGHTFACE_MODEL_PACK', default='buffalo_l'),
    'ONNX_PROVIDERS': env('ONNX_PROVIDERS', default='CPUExecutionProvider').split(','),
}

FACE_MATCH_THRESHOLD_VERIFIED = env('FACE_MATCH_THRESHOLD_VERIFIED')
FACE_MATCH_THRESHOLD_REVIEW = env('FACE_MATCH_THRESHOLD_REVIEW')


def _parse_face_match_weights(raw: str) -> dict:
    weights = {}
    for item in raw.split(','):
        if ':' not in item:
            continue
        key, value = item.split(':', 1)
        try:
            weights[key.strip()] = float(value)
        except ValueError:
            continue
    return weights or {'straight': 0.5, 'left': 0.2, 'right': 0.2, 'up': 0.1}


FACE_MATCH_WEIGHTS = _parse_face_match_weights(env('FACE_MATCH_WEIGHTS'))

# LIVENESS SETTINGS
LIVENESS = {
    'BLINK_THRESHOLD': env('LIVENESS_BLINK_THRESHOLD', default=0.25),
    'HEAD_YAW_LEFT': env('HEAD_YAW_LEFT'),
    'HEAD_YAW_RIGHT': env('HEAD_YAW_RIGHT'),
    'HEAD_PITCH_UP': env('HEAD_PITCH_UP'),
    'CHALLENGE_COUNT': env('CHALLENGE_COUNT'),
    'CHALLENGE_TIMEOUT': env('LIVENESS_CHALLENGE_TIMEOUT', default=30),
    'MAX_RETRIES': env('LIVENESS_MAX_RETRIES', default=3),
    'CHALLENGES': ['look_left', 'look_right', 'look_up'],
}

HEAD_YAW_LEFT = env('HEAD_YAW_LEFT')
HEAD_YAW_RIGHT = env('HEAD_YAW_RIGHT')
HEAD_PITCH_UP = env('HEAD_PITCH_UP')
CHALLENGE_COUNT = env('CHALLENGE_COUNT')

# QR CODE SETTINGS
QR_CODE = {
    'BASE_URL': env('QR_BASE_URL', default='https://faceid.akhu.uz/verify/qr/'),
    'TOKEN_EXPIRY_DAYS': env('QR_TOKEN_EXPIRY_DAYS', default=365),
    'SECRET': SECRET_KEY,
}
# FACE QUALITY SETTINGS (FQA)
FACE_QUALITY = {
    "MIN_BLUR": 25,
    "MIN_BRIGHTNESS": 45,
    "MAX_BRIGHTNESS": 230,
    "MIN_FACE_SIZE": 0.10,
    "MAX_CENTER_OFFSET": 0.30,
    "MIN_DETECTION_CONFIDENCE": 0.65,
}

# FACE ANTI-SPOOFING SETTINGS
ANTI_SPOOF = {
    "MODEL": "MiniFASNet",
    "LIVE_THRESHOLD": 0.85,
    "MODEL_PATH": os.path.join(BASE_DIR, "apps", "face_engine", "models", "MiniFASNetV2.onnx"),
}

# SITE SETTINGS
SITE_NAME = env('SITE_NAME', default='AKHU Face Verification System')
SITE_URL = env('SITE_URL', default='https://faceid.akhu.uz')
INSTITUTION_NAME = env('INSTITUTION_NAME', default='Andijan Khusan University')

# LOGIN URLS
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
SUPERVISOR_LOGIN_URL = '/supervisor/login/'
ADMIN_PANEL_LOGIN_URL = '/admin-panel/login/'

# FILE UPLOAD
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB

ALLOWED_DOCUMENT_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.pdf']
ALLOWED_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png']
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
