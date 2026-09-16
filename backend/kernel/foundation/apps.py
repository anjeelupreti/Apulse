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
        _load_bs_calendar()


def _load_bs_calendar() -> None:
    """Load the Bikram Sambat table named by settings, if one is configured.

    A malformed table stops the process rather than being skipped: running without BS dates is a
    visible failure, whereas running with wrong ones puts wrong dates on tax invoices.
    """
    from django.conf import settings

    path = getattr(settings, "BS_CALENDAR_FILE", "")
    if not path:
        return

    from shared.nepali_calendar import load_table, load_table_from_json

    load_table(load_table_from_json(path))
