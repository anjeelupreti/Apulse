"""Production settings. Everything sensitive must come from the environment."""

import sentry_sdk
from django.core.exceptions import ImproperlyConfigured

from ._env import env
from .base import *

DEBUG = False

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("BACKEND_ALLOWED_HOSTS must be set in production.")
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("BACKEND_SECRET_KEY must be at least 50 characters.")

# ------------------------------------------------------------------ transport security
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("BACKEND_SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^healthz$", r"^readyz$"]
SECURE_HSTS_SECONDS = env.int("BACKEND_HSTS_SECONDS", default=31_536_000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# Preload is a one-way door: browsers hard-code the domain and removal takes months.
# Enable deliberately once every tenant subdomain is known to be HTTPS-only.
SECURE_HSTS_PRELOAD = False
SILENCED_SYSTEM_CHECKS = ["security.W021"]
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"

# API docs are not public in production.
SPECTACULAR_SETTINGS = {
    **SPECTACULAR_SETTINGS,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"],
}

# ------------------------------------------------------------------ error tracking
_sentry_dsn = env.str("BACKEND_SENTRY_DSN", default="")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        environment=ENVIRONMENT,
        release=f"npms-backend@{APP_VERSION}+{GIT_SHA}",
        traces_sample_rate=env.float("BACKEND_SENTRY_TRACES_SAMPLE_RATE", default=0.0),
        send_default_pii=False,
    )
