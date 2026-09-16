"""Structured logging (structlog) shared by Django, Celery and management commands."""

from collections.abc import MutableMapping
from typing import Any

import structlog

from shared.redaction import MASK, is_sensitive


def redact_sensitive(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Mask values of well-known secret keys so they never reach log storage."""
    for key in event_dict:
        if is_sensitive(key):
            event_dict[key] = MASK
    return event_dict


def build_logging(*, json_logs: bool, level: str) -> dict[str, Any]:
    """Configure structlog and return a Django `LOGGING` dict routing stdlib logs through it."""
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_sensitive,
    ]
    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    final_processors: list[Any] = [structlog.stdlib.ProcessorFormatter.remove_processors_meta]
    if json_logs:
        final_processors += [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        final_processors.append(structlog.dev.ConsoleRenderer())

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structlog": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": final_processors,
                "foreign_pre_chain": shared_processors,
            }
        },
        "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "structlog"}},
        "root": {"handlers": ["console"], "level": level},
        "loggers": {
            "django.db.backends": {"level": "WARNING"},
            "django.server": {"level": "INFO"},
            "celery": {"level": level},
        },
    }
