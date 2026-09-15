"""Base class for every Celery task: retries with backoff and request-id propagation."""

from typing import Any

import structlog
from celery import Task

REQUEST_ID_HEADER = "request_id"


class BaseTask(Task):
    acks_late = True
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
    max_retries = 5

    def apply_async(
        self,
        args: Any = None,
        kwargs: Any = None,
        **options: Any,
    ) -> Any:
        request_id = structlog.contextvars.get_contextvars().get("request_id")
        if request_id:
            headers = options.setdefault("headers", {}) or {}
            headers.setdefault(REQUEST_ID_HEADER, request_id)
            options["headers"] = headers
        return super().apply_async(args, kwargs, **options)

    def before_start(self, task_id: str, args: Any, kwargs: Any) -> None:  # noqa: ARG002 (Celery signature)
        request_id = getattr(self.request, REQUEST_ID_HEADER, None) or (
            self.request.headers or {}
        ).get(REQUEST_ID_HEADER)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            task_id=task_id, task=self.name, request_id=request_id
        )
