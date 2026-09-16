"""The counter flow over HTTP, end to end.

Not a re-test of the rules — those are covered where they live. What this checks is that the rules
are still in force when reached through a request, that a refusal comes back as the envelope a
screen can read, and that a retried request does not bill anybody twice.
"""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from core.sales.models import InvoiceStatus
from kernel.identity.models import User
from kernel.rbac import services as rbac
from kernel.rbac.models import Role
from kernel.tenancy.context import tenant_context
from kernel.tenancy.models import Location, TenantMembership

from .conftest import TODAY, stock_up

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("calendar", "document_types", "inside_tenant"),
]


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


def member_of(provisioned, *, email, role_code, name="Staff"):
    """A signed-up user of this account, holding one of its built-in roles."""
    user = User.objects.create_user(email, "s3cure-pass-phrase", full_name=name)
    TenantMembership.objects.create(
        tenant=provisioned.tenant, user=user, status=TenantMembership.Status.ACTIVE
    )
    with tenant_context(provisioned.tenant.id):
        rbac.assign_role(user=user, role=Role.objects.get(code=role_code))
    return user


def api_for(user, provisioned):
    api = APIClient()
    api.force_authenticate(user)
    api.defaults["HTTP_HOST"] = f"{provisioned.tenant.slug}.testserver"
    return api


@pytest.fixture
def owner(provisioned):
    """Holds every permission in the account."""
    return member_of(provisioned, email="owner@example.com", role_code="owner", name="Owner")


@pytest.fixture
def client(owner, provisioned):
    return api_for(owner, provisioned)


@pytest.fixture
def counter(branch):
    return Location.objects.get(branch=branch, code="COUNTER")


def start(client, branch, counter):
    return client.post(
        "/api/v1/sales/invoices/",
        {"branch": str(branch.pk), "location": str(counter.pk), "invoice_date": str(TODAY)},
        format="json",
    )


def add(client, invoice_id, item, quantity="4"):
    return client.post(
        f"/api/v1/sales/invoices/{invoice_id}/lines/",
        {"item": str(item.pk), "quantity": quantity},
        format="json",
    )


def issue(client, invoice_id, key="till-1-0001"):
    return client.post(
        f"/api/v1/sales/invoices/{invoice_id}/issue/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )


# --------------------------------------------------------------------------- the whole flow
def test_a_bill_can_be_built_and_issued_over_http(client, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000)

    draft = start(client, branch, counter)
    assert draft.status_code == 201
    assert draft.json()["status"] == InvoiceStatus.DRAFT
    assert draft.json()["number"] == ""

    line = add(client, draft.json()["id"], paracetamol)
    assert line.status_code == 201
    assert line.json()["item_name"] == "Paracetamol 500mg"

    issued = issue(client, draft.json()["id"])
    assert issued.status_code == 200

    body = issued.json()
    assert body["status"] == InvoiceStatus.ISSUED
    assert body["number"]
    assert body["payable_amount"] == "80.00"
    assert body["amount_outstanding"] == "80.00"
    assert body["amount_in_words"] == "Eighty rupees only"


def test_the_batch_that_went_out_comes_back_on_the_line(client, paracetamol, branch, counter):
    """What a recall is answered from, so the counter can see it too."""
    stock_up(paracetamol, branch, counter, 1000)
    draft = start(client, branch, counter).json()
    add(client, draft["id"], paracetamol)
    issued = issue(client, draft["id"]).json()

    allocations = issued["lines"][0]["allocations"]
    assert allocations[0]["batch_number"] == "B1"
    assert allocations[0]["expiry_date"]


def test_amounts_come_back_as_strings_not_numbers(client, paracetamol, branch, counter):
    """A total that round-trips through a JSON number has been quietly rounded."""
    stock_up(paracetamol, branch, counter, 1000)
    draft = start(client, branch, counter).json()
    add(client, draft["id"], paracetamol)
    body = issue(client, draft["id"]).json()

    assert isinstance(body["payable_amount"], str)
    assert isinstance(body["lines"][0]["rate"], str)


# --------------------------------------------------------------------------- retries
def test_issuing_twice_with_the_same_key_issues_one_bill(client, paracetamol, branch, counter):
    """The connection stalled and the till pressed again."""
    stock_up(paracetamol, branch, counter, 1000)
    draft = start(client, branch, counter).json()
    add(client, draft["id"], paracetamol)

    first = issue(client, draft["id"], key="till-1-0007")
    second = issue(client, draft["id"], key="till-1-0007")

    assert first.json()["number"] == second.json()["number"]
    assert second["Idempotent-Replay"] == "true"


def test_issuing_needs_an_idempotency_key(client, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000)
    draft = start(client, branch, counter).json()
    add(client, draft["id"], paracetamol)

    response = client.post(f"/api/v1/sales/invoices/{draft['id']}/issue/", {}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_a_second_issue_without_the_key_is_refused_by_the_rules(
    client, paracetamol, branch, counter
):
    """Belt and braces: even without idempotency, an issued bill cannot be issued again."""
    stock_up(paracetamol, branch, counter, 1000)
    draft = start(client, branch, counter).json()
    add(client, draft["id"], paracetamol)
    issue(client, draft["id"], key="a")

    response = issue(client, draft["id"], key="b")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVOICE_NOT_EDITABLE"


# --------------------------------------------------------------------------- refusals read well
def test_an_issued_bill_takes_no_more_lines(client, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000)
    draft = start(client, branch, counter).json()
    add(client, draft["id"], paracetamol)
    issue(client, draft["id"])

    response = add(client, draft["id"], paracetamol)
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INVOICE_NOT_EDITABLE"
    assert error["message_ne"]


def test_an_empty_bill_cannot_be_issued(client, branch, counter):
    draft = start(client, branch, counter).json()
    response = issue(client, draft["id"])

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVOICE_HAS_NO_LINES"


def test_selling_above_the_printed_price_is_refused(client, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000)
    draft = start(client, branch, counter).json()

    response = client.post(
        f"/api/v1/sales/invoices/{draft['id']}/lines/",
        {"item": str(paracetamol.pk), "quantity": "1", "rate": "999"},
        format="json",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PRICE_ABOVE_MRP"


def test_a_bad_payload_comes_back_with_the_field_that_was_wrong(client, branch, counter):
    response = client.post(
        "/api/v1/sales/invoices/",
        {"branch": str(branch.pk)},  # no location
        format="json",
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert {detail["field"] for detail in error["details"]} == {"location"}


# --------------------------------------------------------------------------- crediting
def test_a_bill_can_be_credited_in_one_call(client, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000)
    draft = start(client, branch, counter).json()
    add(client, draft["id"], paracetamol)
    issued = issue(client, draft["id"]).json()

    response = client.post(
        f"/api/v1/sales/invoices/{draft['id']}/credit-note/",
        {"reason": "Returned unopened", "confirmed": True},
        format="json",
        HTTP_IDEMPOTENCY_KEY="credit-1",
    )
    assert response.status_code == 201
    note = response.json()
    assert note["number"]
    assert note["payable_amount"] == issued["payable_amount"]
    assert note["invoice_number"] == issued["number"]


def test_crediting_without_confirming_is_refused(client, paracetamol, branch, counter):
    """It issues a numbered tax document and moves stock. It gets asked out loud."""
    stock_up(paracetamol, branch, counter, 1000)
    draft = start(client, branch, counter).json()
    add(client, draft["id"], paracetamol)
    issue(client, draft["id"])

    response = client.post(
        f"/api/v1/sales/invoices/{draft['id']}/credit-note/",
        {"reason": "Returned", "confirmed": False},
        format="json",
        HTTP_IDEMPOTENCY_KEY="credit-2",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CREDIT_NOTE_NEEDS_CONFIRMATION"


def test_cancelling_issues_the_credit_note_that_evidences_it(client, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000)
    draft = start(client, branch, counter).json()
    add(client, draft["id"], paracetamol)
    issue(client, draft["id"])

    cancelled = client.post(
        f"/api/v1/sales/invoices/{draft['id']}/cancel/",
        {"reason": "Rung up twice"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="cancel-1",
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == InvoiceStatus.CANCELLED

    notes = client.get("/api/v1/sales/credit-notes/").json()
    assert notes["count"] == 1
    assert notes["results"][0]["kind"] == "cancellation"


# --------------------------------------------------------------------------- reading
def test_bills_can_be_listed_and_searched(client, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000)
    draft = start(client, branch, counter).json()
    add(client, draft["id"], paracetamol)
    issued = issue(client, draft["id"]).json()

    listed = client.get("/api/v1/sales/invoices/", {"search": issued["number"]}).json()
    assert listed["count"] == 1
    assert listed["results"][0]["id"] == issued["id"]


def test_a_date_range_narrows_the_list(client, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000)
    draft = start(client, branch, counter).json()
    add(client, draft["id"], paracetamol)
    issue(client, draft["id"])

    inside = client.get(
        "/api/v1/sales/invoices/", {"date_from": str(TODAY), "date_to": str(TODAY)}
    ).json()
    outside = client.get("/api/v1/sales/invoices/", {"date_from": "2030-01-01"}).json()

    assert inside["count"] == 1
    assert outside["count"] == 0


def test_a_reprint_is_counted_and_marked_as_a_copy(client, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, 1000)
    draft = start(client, branch, counter).json()
    add(client, draft["id"], paracetamol)
    issue(client, draft["id"])

    first = client.post(f"/api/v1/sales/invoices/{draft['id']}/reprint/").json()
    assert first["is_copy"] is False

    second = client.post(f"/api/v1/sales/invoices/{draft['id']}/reprint/").json()
    assert second["is_copy"] is True
    assert second["print_count"] == 2


# --------------------------------------------------------------------------- who may do what
def test_signing_in_is_required(provisioned):
    anonymous = APIClient()
    anonymous.defaults["HTTP_HOST"] = f"{provisioned.tenant.slug}.testserver"

    response = anonymous.get("/api/v1/sales/invoices/")
    assert response.status_code in (401, 403)
    assert response.json()["error"]["code"] in ("AUTH_NOT_AUTHENTICATED", "PERMISSION_DENIED")


def test_a_counter_assistant_cannot_cancel_a_bill(provisioned, paracetamol, branch, counter):
    """Cancelling a tax document is not a counter decision."""
    assistant = member_of(
        provisioned, email="counter@example.com", role_code="counter_staff", name="Counter"
    )
    api = api_for(assistant, provisioned)

    stock_up(paracetamol, branch, counter, 1000)
    draft = start(api, branch, counter).json()
    add(api, draft["id"], paracetamol)
    issue(api, draft["id"])

    response = api.post(
        f"/api/v1/sales/invoices/{draft['id']}/cancel/",
        {"reason": "Because"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="nope",
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_one_pharmacy_cannot_read_anothers_bills(client, paracetamol, branch, counter):
    from kernel.tenancy.tests.factories import make_tenant

    stock_up(paracetamol, branch, counter, 1000)
    draft = start(client, branch, counter).json()
    add(client, draft["id"], paracetamol)
    issue(client, draft["id"])

    bravo = make_tenant("bravo")
    intruder = member_of(bravo, email="b@example.com", role_code="owner", name="B")
    api = api_for(intruder, bravo)

    assert api.get("/api/v1/sales/invoices/").json()["count"] == 0
    assert api.get(f"/api/v1/sales/invoices/{draft['id']}/").status_code == 404
