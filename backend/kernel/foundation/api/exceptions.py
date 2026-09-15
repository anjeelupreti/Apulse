"""Render every API error as the standard envelope (docs/CONVENTIONS.md §4.3)."""

from typing import Any

import structlog
from django.conf import settings
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from shared.errors import DomainError, ErrorCode, codes

logger = structlog.get_logger(__name__)

_DRF_ERROR_CODES: tuple[tuple[type[exceptions.APIException], ErrorCode], ...] = (
    (exceptions.NotAuthenticated, codes.AUTH_NOT_AUTHENTICATED),
    (exceptions.AuthenticationFailed, codes.AUTH_FAILED),
    (exceptions.PermissionDenied, codes.PERMISSION_DENIED),
    (exceptions.NotFound, codes.NOT_FOUND),
    (exceptions.MethodNotAllowed, codes.METHOD_NOT_ALLOWED),
    (exceptions.NotAcceptable, codes.NOT_ACCEPTABLE),
    (exceptions.UnsupportedMediaType, codes.UNSUPPORTED_MEDIA_TYPE),
    (exceptions.Throttled, codes.RATE_LIMITED),
    (exceptions.ParseError, codes.MALFORMED_REQUEST),
    (exceptions.ValidationError, codes.VALIDATION_ERROR),
)

_STATUS_FALLBACK: dict[int, ErrorCode] = {
    401: codes.AUTH_NOT_AUTHENTICATED,
    403: codes.PERMISSION_DENIED,
    404: codes.NOT_FOUND,
}


def envelope(
    error: ErrorCode, message: str, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "error": {
            "code": error.code,
            "message": message,
            "message_ne": error.message_ne,
            "details": details or [],
            "request_id": structlog.contextvars.get_contextvars().get("request_id"),
        }
    }


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, DomainError):
        return Response(envelope(exc.error, exc.message, exc.details), status=exc.http_status)

    # DRF converts Django's Http404 / PermissionDenied and sets headers (Retry-After etc.).
    response = drf_exception_handler(exc, context)
    if response is None:
        if settings.DEBUG:
            return None  # let Django show the traceback page
        logger.exception("unhandled_api_exception", view=type(context.get("view")).__name__)
        return Response(envelope(codes.SERVER_ERROR, codes.SERVER_ERROR.message_en), status=500)

    error = _error_for(exc, response.status_code)
    details = (
        _flatten_validation(response.data) if isinstance(exc, exceptions.ValidationError) else []
    )
    response.data = envelope(error, error.message_en, details)
    return response


def _error_for(exc: Exception, status_code: int) -> ErrorCode:
    for exc_type, error in _DRF_ERROR_CODES:
        if isinstance(exc, exc_type):
            return error
    if status_code in _STATUS_FALLBACK:
        return _STATUS_FALLBACK[status_code]
    return codes.SERVER_ERROR if status_code >= 500 else codes.VALIDATION_ERROR


def _flatten_validation(data: Any, prefix: str = "") -> list[dict[str, Any]]:
    """Flatten DRF's nested errors to `[{field, code, message}]` with dotted/indexed paths."""
    if isinstance(data, dict):
        flattened: list[dict[str, Any]] = []
        for key, value in data.items():
            if isinstance(key, int):
                # DRF reports errors for a `many=True` child as {index: {...}}.
                path = f"{prefix}[{key}]"
            else:
                name = "" if key in ("non_field_errors", "detail") else str(key)
                path = f"{prefix}.{name}" if prefix and name else (name or prefix)
            flattened.extend(_flatten_validation(value, path))
        return flattened
    if isinstance(data, list):
        flattened = []
        for index, item in enumerate(data):
            if isinstance(item, dict | list):
                flattened.extend(_flatten_validation(item, f"{prefix}[{index}]"))
            else:
                flattened.append(
                    {
                        "field": prefix or None,
                        "code": getattr(item, "code", "invalid"),
                        "message": str(item),
                    }
                )
        return flattened
    return [
        {"field": prefix or None, "code": getattr(data, "code", "invalid"), "message": str(data)}
    ]
