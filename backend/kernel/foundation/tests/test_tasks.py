import structlog
from celery import shared_task


@shared_task(name="tests.echo_request_id")
def echo_request_id():
    return structlog.contextvars.get_contextvars().get("request_id")


def test_request_id_propagates_from_caller_into_task():
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="req-propagated-1")
    try:
        assert echo_request_id.delay().get() == "req-propagated-1"
    finally:
        structlog.contextvars.clear_contextvars()


def test_task_base_class_is_applied():
    from kernel.foundation.tasks import BaseTask

    assert isinstance(echo_request_id, BaseTask)
    assert echo_request_id.acks_late is True
