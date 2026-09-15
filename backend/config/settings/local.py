"""Local development settings. Safe defaults so `python tasks.py dev` works out of the box."""

import os

from ._env import load_env_file

load_env_file()

_LOCAL_DEFAULTS = {
    "BACKEND_ENVIRONMENT": "local",
    "BACKEND_SECRET_KEY": "insecure-local-development-key-do-not-use-anywhere-else",
    "BACKEND_DEBUG": "true",
    "BACKEND_ALLOWED_HOSTS": "localhost,127.0.0.1,.localhost",
    "BACKEND_ADMIN_ENABLED": "true",
    "BACKEND_DATABASE_URL": "postgres://npms_app:npms_app@localhost:55432/npms",
    "BACKEND_REDIS_URL": "redis://localhost:56379/0",
    "BACKEND_CELERY_BROKER_URL": "redis://localhost:56379/1",
    "BACKEND_EMAIL_URL": "smtp://localhost:51025",
    "BACKEND_TENANT_BASE_DOMAIN": "localhost",
    "BACKEND_CORS_ALLOWED_ORIGINS": "http://localhost:3000,http://localhost:3001",
    "BACKEND_CSRF_TRUSTED_ORIGINS": "http://localhost:3000,http://localhost:3001",
    "BACKEND_LOG_JSON": "false",
}
for _key, _value in _LOCAL_DEFAULTS.items():
    os.environ.setdefault(_key, _value)

from .base import *

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]
