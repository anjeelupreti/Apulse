"""Exception raised by services for business-rule violations."""

from .catalogue import ErrorCode, get


class DomainError(Exception):
    """A rule violation with a registered code; rendered by the API as the standard envelope."""

    def __init__(
        self,
        code: str | ErrorCode,
        message: str | None = None,
        *,
        details: list[dict[str, str]] | None = None,
    ) -> None:
        self.error = code if isinstance(code, ErrorCode) else get(code)
        self.message = message or self.error.message_en
        self.details = details or []
        super().__init__(self.message)

    @property
    def http_status(self) -> int:
        return self.error.http_status
