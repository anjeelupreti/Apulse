"""Capture the caller's details for anything audited during this request."""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from .context import AuditContext, reset_context, set_context


class AuditContextMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        token = set_context(
            AuditContext(
                request_id=getattr(request, "request_id", ""),
                ip_address=request.META.get("REMOTE_ADDR", "") or "",
                user_agent=request.headers.get("User-Agent", "")[:400],
                device_id=request.headers.get("X-Device-Id", "")[:64],
                actor=getattr(request, "user", None),
            )
        )
        try:
            return self.get_response(request)
        finally:
            reset_context(token)
