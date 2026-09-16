"""Stopping two people from silently overwriting each other.

Two pharmacists open the same medicine, one changes its price, the other changes its storage note
and saves a minute later. Last-write-wins means the price change disappears with no trace and no
warning, and it is discovered when a customer is charged the old amount.

So an edit says which version it was made against. If the row has moved on since, the edit is
refused and the person is told to reload — annoying once, rather than wrong quietly.

Two ways to send it, and both are accepted because they suit different callers: a `version` field
in the body, which is what a form posts, and an `If-Match` header, which is what a generated HTTP
client does.
"""

from typing import Any

from rest_framework.request import Request

from shared.errors import DomainError

from . import errors

IF_MATCH = "If-Match"
ETAG = "ETag"


def etag_for(instance: Any) -> str:
    return f'W/"{getattr(instance, "version", 0)}"'


def requested_version(request: Request) -> int | None:
    """The version the caller believes they are editing, from the body or the header."""
    body = getattr(request, "data", None)
    if isinstance(body, dict) and body.get("version") is not None:
        try:
            return int(body["version"])
        except (TypeError, ValueError):
            raise DomainError(errors.VERSION_REQUIRED) from None

    header = request.headers.get(IF_MATCH, "").strip()
    if not header:
        return None
    # Accepts both `W/"3"` and a bare `3`, because a client that sends the ETag back verbatim and
    # one that sends the number should both work.
    digits = "".join(character for character in header if character.isdigit())
    return int(digits) if digits else None


def check(instance: Any, request: Request, *, required: bool = True) -> None:
    """Refuse the edit if the row has moved on since the caller read it."""
    current = getattr(instance, "version", None)
    if current is None:
        return  # not a versioned model; nothing to check

    asked = requested_version(request)
    if asked is None:
        if required:
            raise DomainError(errors.VERSION_REQUIRED)
        return
    if asked != current:
        raise DomainError(
            errors.VERSION_CONFLICT,
            f"You are editing version {asked}; it is now at version {current}.",
        )


def bump(instance: Any) -> None:
    """Move a versioned row on by one. Called by the service that saved it."""
    if hasattr(instance, "version"):
        instance.version = (instance.version or 0) + 1


class VersionedUpdateMixin:
    """Adds the check to a DRF update, and the current ETag to the response."""

    version_required_on_update = True

    def perform_precondition_check(self, instance: Any) -> None:
        check(
            instance,
            self.request,  # type: ignore[attr-defined]
            required=self.version_required_on_update,
        )

    def finalize_response(self, request: Request, response: Any, *args: Any, **kwargs: Any) -> Any:
        response = super().finalize_response(request, response, *args, **kwargs)  # type: ignore[misc]
        instance = getattr(self, "_versioned_instance", None)
        if instance is not None:
            response[ETAG] = etag_for(instance)
        return response
