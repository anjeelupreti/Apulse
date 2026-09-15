"""Request correlation and logging context."""

import re
from collections.abc import Callable

import structlog
from django.http import HttpRequest, HttpResponse

from shared.ids import uuid7

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{8,64}")


class RequestIdMiddleware:
    """Accept a well-formed incoming X-Request-ID or mint one; bind it to all logs; echo it back."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_REQUEST_ID.fullmatch(incoming) else uuid7().hex
        request.request_id = request_id  # type: ignore[attr-defined]

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = self.get_response(request)
        response[REQUEST_ID_HEADER] = request_id
        return response


class LogContextMiddleware:
    """Bind the authenticated user (session auth) to the logging context."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            structlog.contextvars.bind_contextvars(user_id=str(user.pk))
        return self.get_response(request)
