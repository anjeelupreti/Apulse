"""Test settings. Runs against real PostgreSQL (RLS and extensions must be exercised)."""

import os

from ._env import load_env_file

load_env_file()

_TEST_DEFAULTS = {
    "BACKEND_ENVIRONMENT": "test",
    "BACKEND_SECRET_KEY": "insecure-test-key",
    "BACKEND_DATABASE_URL": "postgres://npms_app:npms_app@localhost:55432/npms",
    "BACKEND_REDIS_URL": "redis://localhost:56379/0",
    "BACKEND_CELERY_BROKER_URL": "memory://",
    "BACKEND_TENANT_BASE_DOMAIN": "testserver",
}
for _key, _value in _TEST_DEFAULTS.items():
    os.environ.setdefault(_key, _value)

from config.logging import build_logging

from .base import *

ENVIRONMENT = "test"
DEBUG = False
ALLOWED_HOSTS = ["testserver", ".testserver", "localhost", ".localhost"]

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
STORAGES = {
    **STORAGES,
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}

LOGGING = build_logging(json_logs=False, level="WARNING")
