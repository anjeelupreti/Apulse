"""Domain errors and the platform-wide error code catalogue."""

from . import codes
from .catalogue import ErrorCode, all_codes, get, register
from .exceptions import DomainError

__all__ = ("DomainError", "ErrorCode", "all_codes", "codes", "get", "register")
