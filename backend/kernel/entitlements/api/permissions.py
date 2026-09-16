"""DRF permission classes for plan entitlements.

Separate from the access-control classes on purpose. "Your role does not allow this" and "your
plan does not include this" are different problems with different answers: one is for the pharmacy
owner to fix, the other is a conversation with us.
"""

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from .. import resolver


class HasFeature(BasePermission):
    """Checks the codes listed in the view's `required_features`."""

    def has_permission(self, request: Request, view: APIView) -> bool:  # noqa: ARG002 (DRF)
        for code in tuple(getattr(view, "required_features", ())):
            resolver.require_feature(code)
        return True


class HasModule(BasePermission):
    """Checks the view's `required_module`."""

    def has_permission(self, request: Request, view: APIView) -> bool:  # noqa: ARG002 (DRF)
        code = getattr(view, "required_module", "")
        if code:
            resolver.require_module(code)
        return True


def RequireFeature(*codes: str) -> type[BasePermission]:  # noqa: N802 (a class factory)
    """Inline form: `permission_classes = [RequireFeature("pharmacy.offline_pos")]`."""

    class _RequireFeature(BasePermission):
        def has_permission(self, request: Request, view: APIView) -> bool:  # noqa: ARG002
            for code in codes:
                resolver.require_feature(code)
            return True

    return _RequireFeature
