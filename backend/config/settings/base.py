"""Settings shared by every environment.

All configuration comes from environment variables prefixed with ``BACKEND_``.
Required variables have no default so a misconfigured deployment fails at startup.
"""

from typing import Any

import django_stubs_ext

from config.logging import build_logging

from ._env import BASE_DIR, env, load_env_file

load_env_file()

# Django's generics (QuerySet[Model], ModelAdmin[Model], ...) exist only in type stubs.
# This makes them subscriptable at runtime so annotations do not need string quoting.
django_stubs_ext.monkeypatch()

# ------------------------------------------------------------------ identity of the build
ENVIRONMENT = env.str("BACKEND_ENVIRONMENT")
APP_VERSION = env.str("BACKEND_APP_VERSION", default="0.1.0-dev")
GIT_SHA = env.str("BACKEND_GIT_SHA", default="") or "unknown"
BUILD_TIME = env.str("BACKEND_BUILD_TIME", default="") or "unknown"

# ------------------------------------------------------------------ core
SECRET_KEY = env.str("BACKEND_SECRET_KEY")
DEBUG = env.bool("BACKEND_DEBUG", default=False)
ALLOWED_HOSTS = env.list("BACKEND_ALLOWED_HOSTS", default=[])
ADMIN_ENABLED = env.bool("BACKEND_ADMIN_ENABLED", default=False)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # third party
    "corsheaders",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "django_celery_beat",
    "django_celery_results",
    "channels",
    # kernel
    "kernel.foundation",
    "kernel.geo",
    "kernel.identity",
    "kernel.tenancy",
    "kernel.rbac",
]

MIDDLEWARE = [
    "kernel.foundation.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "kernel.tenancy.middleware.TenantMiddleware",
    "kernel.foundation.middleware.LogContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ------------------------------------------------------------------ database
DATABASES = {"default": env.db_url("BACKEND_DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
DATABASES["default"]["CONN_MAX_AGE"] = env.int("BACKEND_DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
# Domain models declare UUIDv7 primary keys explicitly (kernel.foundation.models.UUIDModel).
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------ auth
AUTH_USER_MODEL = "identity.User"
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
SESSION_COOKIE_NAME = "npms_session"
CSRF_COOKIE_NAME = "npms_csrftoken"

# Sign in with an email address or a phone number: counter staff often have no email.
AUTHENTICATION_BACKENDS = ["kernel.identity.backends.EmailOrPhoneBackend"]

# Sign-in throttling. Counters are keyed on the identifier as typed and on the client IP, so a
# lockout response never reveals whether an account exists.
LOGIN_MAX_FAILED_ATTEMPTS = env.int("BACKEND_LOGIN_MAX_FAILED_ATTEMPTS", default=5)
LOGIN_MAX_FAILED_ATTEMPTS_PER_IP = env.int("BACKEND_LOGIN_MAX_FAILED_ATTEMPTS_PER_IP", default=20)
LOGIN_LOCKOUT_SECONDS = env.int("BACKEND_LOGIN_LOCKOUT_SECONDS", default=900)
# Only enable behind a proxy that overwrites X-Forwarded-For; otherwise a client can spoof its IP.
LOGIN_TRUST_FORWARDED_FOR = env.bool("BACKEND_LOGIN_TRUST_FORWARDED_FOR", default=False)
TWO_FACTOR_ISSUER = env.str("BACKEND_TWO_FACTOR_ISSUER", default="NPMS")

# ------------------------------------------------------------------ i18n / time
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("ne", "नेपाली")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Asia/Kathmandu"
USE_I18N = True
USE_TZ = True

# ------------------------------------------------------------------ static / files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES: dict[str, dict[str, Any]] = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
if env.bool("BACKEND_USE_S3", default=False):
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env.str("BACKEND_S3_BUCKET_ATTACHMENTS"),
            "endpoint_url": env.str("BACKEND_S3_ENDPOINT_URL", default="") or None,
            "access_key": env.str("BACKEND_S3_ACCESS_KEY_ID"),
            "secret_key": env.str("BACKEND_S3_SECRET_ACCESS_KEY"),
            "region_name": env.str("BACKEND_S3_REGION", default="us-east-1"),
            "default_acl": None,
            "querystring_auth": True,
            "file_overwrite": False,
            "addressing_style": "path",
        },
    }
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# ------------------------------------------------------------------ cache / redis
REDIS_URL = env.str("BACKEND_REDIS_URL")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "npms",
    }
}

# ------------------------------------------------------------------ web security
CORS_ALLOWED_ORIGINS = env.list("BACKEND_CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ["X-Request-ID", "Retry-After"]
CSRF_TRUSTED_ORIGINS = env.list("BACKEND_CSRF_TRUSTED_ORIGINS", default=[])

# ------------------------------------------------------------------ tenancy
# Tenants are addressed as {slug}.{TENANT_BASE_DOMAIN}, or by a verified custom domain.
TENANT_BASE_DOMAIN = env.str("BACKEND_TENANT_BASE_DOMAIN", default="")
# Resolving a tenant from a request header alone lets any caller name any tenant. It stays off
# until tokens carry a verified tenant claim (M2.2).
TENANT_ALLOW_HEADER_RESOLUTION = env.bool("BACKEND_TENANT_ALLOW_HEADER_RESOLUTION", default=False)

# ------------------------------------------------------------------ API
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_PAGINATION_CLASS": "kernel.foundation.api.pagination.DefaultPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env.str("BACKEND_THROTTLE_ANON", default="60/min"),
        "user": env.str("BACKEND_THROTTLE_USER", default="600/min"),
        "login": env.str("BACKEND_THROTTLE_LOGIN", default="10/min"),
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "kernel.foundation.api.exceptions.api_exception_handler",
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
    "COERCE_DECIMAL_TO_STRING": True,
    "DATETIME_FORMAT": "iso-8601",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "NPMS API",
    "DESCRIPTION": "Nepal e-Health Platform — tenant API (pharmacy first).",
    "VERSION": APP_VERSION,
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]+",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
}

# ------------------------------------------------------------------ Celery
CELERY_BROKER_URL = env.str("BACKEND_CELERY_BROKER_URL")
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_RESULT_BACKEND = "django-db"
CELERY_RESULT_EXTENDED = True
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 270
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ------------------------------------------------------------------ Channels
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL], "prefix": "npms:ws"},
    }
}

# ------------------------------------------------------------------ email
vars().update(env.email_url("BACKEND_EMAIL_URL", default="consolemail://"))
DEFAULT_FROM_EMAIL = env.str("BACKEND_DEFAULT_FROM_EMAIL", default="NPMS <no-reply@localhost>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# ------------------------------------------------------------------ logging
LOGGING = build_logging(
    json_logs=env.bool("BACKEND_LOG_JSON", default=True),
    level=env.str("BACKEND_LOG_LEVEL", default="INFO"),
)
