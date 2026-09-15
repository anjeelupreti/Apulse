"""Tenant API v1. Each kernel app / module contributes its own `api/urls.py`."""

from django.urls import include, path

urlpatterns = [
    path("", include("kernel.identity.api.urls")),
]
