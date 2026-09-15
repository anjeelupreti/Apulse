"""Root URL configuration."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from kernel.foundation import health

urlpatterns = [
    path("healthz", health.healthz, name="healthz"),
    path("readyz", health.readyz, name="readyz"),
    path("version", health.version, name="version"),
    path("api/v1/", include("config.api_v1")),
    path("api/schema/", SpectacularAPIView.as_view(), name="openapi-schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="openapi-schema"), name="api-docs"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="openapi-schema"), name="api-redoc"),
]

if settings.ADMIN_ENABLED:
    # Internal debugging only; the product UI lives in the frontend apps.
    urlpatterns.append(path("django-admin/", admin.site.urls))
