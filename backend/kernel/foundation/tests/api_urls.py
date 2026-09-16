"""Throwaway endpoints for exercising idempotency and optimistic concurrency."""

from typing import Any

from django.urls import path
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from kernel.foundation.api import concurrency
from kernel.foundation.api.idempotency import idempotent

#: How many times each view's real work actually ran. A replay must not move these.
CALLS: dict[str, int] = {"create": 0, "required": 0}


def reset() -> None:
    for key in CALLS:
        CALLS[key] = 0


class _OpenView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]


class CreateView(_OpenView):
    @idempotent()
    def post(self, request: Any) -> Response:
        CALLS["create"] += 1
        return Response({"ran": CALLS["create"], "echo": request.data}, status=201)


class RequiredKeyView(_OpenView):
    @idempotent(required=True)
    def post(self, request: Any) -> Response:
        CALLS["required"] += 1
        return Response({"ran": CALLS["required"]}, status=201)


class FailingView(_OpenView):
    @idempotent()
    def post(self, request: Any) -> Response:
        from shared.errors import DomainError, codes

        raise DomainError(codes.VALIDATION_ERROR, "Nope")


class _Thing:
    """Something with a version, standing in for a model row."""

    def __init__(self, version: int = 3) -> None:
        self.version = version


class VersionView(_OpenView):
    def patch(self, request: Any) -> Response:
        thing = _Thing(version=3)
        concurrency.check(thing, request)
        concurrency.bump(thing)
        response = Response({"version": thing.version})
        response[concurrency.ETAG] = concurrency.etag_for(thing)
        return response


class OptionalVersionView(_OpenView):
    def patch(self, request: Any) -> Response:
        concurrency.check(_Thing(version=3), request, required=False)
        return Response({"ok": True})


urlpatterns = [
    path("create/", CreateView.as_view()),
    path("required/", RequiredKeyView.as_view()),
    path("failing/", FailingView.as_view()),
    path("versioned/", VersionView.as_view()),
    path("optional-version/", OptionalVersionView.as_view()),
]
