from typing import Any

from django.apps import AppConfig


def _make_subscriptable(*classes: type) -> None:
    """Allow `Class[Model]` at runtime for classes that are generic only in type stubs."""
    for cls in classes:
        if "__class_getitem__" not in cls.__dict__:
            cls.__class_getitem__ = classmethod(lambda c, *_args: c)  # type: ignore[attr-defined]


class FoundationConfig(AppConfig):
    name = "kernel.foundation"
    label = "foundation"
    verbose_name = "Kernel foundation"

    def ready(self) -> Any:
        # Django's own classes are patched in settings by django_stubs_ext.monkeypatch();
        # DRF ships no equivalent, so patch the base classes we annotate with.
        from rest_framework import generics, serializers, viewsets

        _make_subscriptable(
            serializers.BaseSerializer,
            generics.GenericAPIView,
            viewsets.GenericViewSet,
        )
