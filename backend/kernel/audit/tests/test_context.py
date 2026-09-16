import pytest
from django.test import RequestFactory

from kernel.audit.context import AuditContext, audit_context, get_context
from kernel.audit.middleware import AuditContextMiddleware
from kernel.audit.models import AuditAction
from kernel.audit.services import record
from kernel.tenancy.context import tenant_context
from kernel.tenancy.tests.factories import make_tenant


def test_no_context_by_default():
    assert get_context() == AuditContext()
    assert get_context().as_dict() == {}


def test_the_middleware_captures_who_the_caller_was():
    captured: dict[str, object] = {}

    def view(_request):
        captured["context"] = get_context()
        return "response"

    request = RequestFactory().get(
        "/", headers={"user-agent": "POS/1.0", "x-device-id": "counter-2"}
    )
    request.request_id = "req-abcdef12"
    request.META["REMOTE_ADDR"] = "10.0.0.7"

    assert AuditContextMiddleware(view)(request) == "response"

    context = captured["context"]
    assert context.request_id == "req-abcdef12"
    assert context.ip_address == "10.0.0.7"
    assert context.user_agent == "POS/1.0"
    assert context.device_id == "counter-2"


def test_the_context_does_not_outlive_the_request():
    def view(_request):
        return "response"

    request = RequestFactory().get("/")
    request.request_id = "req-abcdef12"
    AuditContextMiddleware(view)(request)

    assert get_context() == AuditContext()


def test_background_work_can_describe_itself():
    with audit_context(request_id="job-1", task="nightly_expiry_check") as context:
        assert context.as_dict() == {"request_id": "job-1", "task": "nightly_expiry_check"}
    assert get_context() == AuditContext()


@pytest.mark.django_db
def test_recorded_entries_carry_the_caller_details():
    tenant = make_tenant("alpha")
    with (
        tenant_context(tenant.tenant.id),
        audit_context(request_id="req-12345678", ip_address="10.0.0.7", user_agent="POS/1.0"),
    ):
        event = record(action=AuditAction.EXPORT, reason="Stock report")

    assert event.context == {
        "request_id": "req-12345678",
        "ip_address": "10.0.0.7",
        "user_agent": "POS/1.0",
    }
