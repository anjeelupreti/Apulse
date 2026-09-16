"""The counter's search, taking the money, and counting the till — over HTTP."""

from decimal import Decimal

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from core.catalog.services import add_barcode
from core.payments.models import ShiftStatus
from kernel.identity.models import User
from kernel.rbac import services as rbac
from kernel.rbac.models import Role
from kernel.tenancy.context import tenant_context
from kernel.tenancy.models import TenantMembership

from .conftest import TODAY, future_expiry, stock_up

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
def pharmacist(provisioned):
    """Can sell, take money, run the till, and give money back."""
    return member_of(
        provisioned, email="rx@example.com", role_code="pharmacist", name="Bimala Gurung"
    )


@pytest.fixture
def client(pharmacist, provisioned):
    return api_for(pharmacist, provisioned)


def bill_of_80(client, branch, counter, paracetamol):
    """An issued bill for 80 rupees, built through the API."""
    stock_up(paracetamol, branch, counter)
    draft = client.post(
        "/api/v1/sales/invoices/",
        {"branch": str(branch.pk), "location": str(counter.pk), "invoice_date": str(TODAY)},
        format="json",
    ).json()
    client.post(
        f"/api/v1/sales/invoices/{draft['id']}/lines/",
        {"item": str(paracetamol.pk), "quantity": "4"},
        format="json",
    )
    return client.post(
        f"/api/v1/sales/invoices/{draft['id']}/issue/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY=f"issue-{draft['id']}",
    ).json()


# --------------------------------------------------------------------------- the counter search
def test_the_counter_search_finds_a_medicine(client, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter)
    results = client.get(
        "/api/v1/catalogue/counter/", {"q": "para", "branch": str(branch.pk)}
    ).json()

    assert len(results) == 1
    assert results[0]["name"] == "Paracetamol 500mg"


def test_the_search_says_whether_there_is_any_and_what_it_costs(
    client, paracetamol, branch, counter
):
    stock_up(paracetamol, branch, counter, expiry_date=future_expiry())
    found = client.get(
        "/api/v1/catalogue/counter/", {"q": "para", "branch": str(branch.pk)}
    ).json()[0]

    assert found["available"] == "1000.000"
    assert found["price"] == "2.0000"
    assert found["nearest_expiry"]


def test_expired_stock_is_on_the_shelf_but_not_available(client, paracetamol, branch, counter):
    """The counter needs both numbers: there is a box there, and it cannot be sold."""
    stock_up(paracetamol, branch, counter)  # expired long ago in real time
    found = client.get(
        "/api/v1/catalogue/counter/", {"q": "para", "branch": str(branch.pk)}
    ).json()[0]

    assert found["on_hand"] == "1000.000"
    assert found["available"] == "0.000"


def test_the_price_quoted_is_the_price_the_bill_will_charge(client, paracetamol, branch, counter):
    """Quoting the item's price while the bill charges the batch's is a support call waiting."""
    stock_up(paracetamol, branch, counter)
    quoted = Decimal(
        client.get("/api/v1/catalogue/counter/", {"q": "para", "branch": str(branch.pk)}).json()[0][
            "price"
        ]
    )

    issued = bill_of_80(client, branch, counter, paracetamol)
    charged_per_tablet = Decimal(issued["lines"][0]["rate"]) / 10  # priced by the strip of ten
    assert charged_per_tablet == quoted


def test_the_search_says_which_pack_is_sold_by_default(client, paracetamol, branch, counter):
    stock_up(paracetamol, branch, counter, expiry_date=future_expiry())
    found = client.get(
        "/api/v1/catalogue/counter/", {"q": "para", "branch": str(branch.pk)}
    ).json()[0]

    assert found["sale_unit"]["code"] == "strip"
    assert Decimal(found["sale_unit"]["factor"]) == 10


def test_stock_is_reported_for_the_branch_that_was_asked_about(
    client, paracetamol, branch, counter, provisioned
):
    """Telling somebody in Birgunj about stock in Kathmandu is worse than telling them nothing."""
    from kernel.tenancy.models import Branch

    other = Branch.objects.create(
        legal_entity=provisioned.legal_entity, code="BR2", name="Second branch"
    )
    stock_up(paracetamol, branch, counter, expiry_date=future_expiry())

    here = client.get("/api/v1/catalogue/counter/", {"branch": str(branch.pk)}).json()[0]
    there = client.get("/api/v1/catalogue/counter/", {"branch": str(other.pk)}).json()[0]

    assert here["available"] == "1000.000"
    assert there["available"] == "0.000"


def test_a_scanned_barcode_returns_the_pack_it_was_on(client, paracetamol, branch, counter):
    """Scanning a box should add a box, not a tablet."""
    from core.catalog.models import ItemUnit

    stock_up(paracetamol, branch, counter)
    strip = ItemUnit.objects.get(item=paracetamol, unit__code="strip")
    add_barcode(paracetamol, "8901234567890", item_unit=strip)

    match = client.post(
        "/api/v1/catalogue/counter/barcode/",
        {"code": "8901234567890"},
        format="json",
    ).json()

    assert match["item"]["name"] == "Paracetamol 500mg"
    assert match["unit"]["code"] == "strip"
    assert match["factor"] == "10.0000"


def test_an_unknown_barcode_comes_back_as_a_domain_error(client):
    response = client.post(
        "/api/v1/catalogue/counter/barcode/", {"code": "nothing-here"}, format="json"
    )
    assert response.status_code >= 400
    assert response.json()["error"]["code"]


# --------------------------------------------------------------------------- taking the money
@pytest.fixture
def shift(client, branch, counter):
    return client.post(
        "/api/v1/payments/shifts/",
        {
            "branch": str(branch.pk),
            "location": str(counter.pk),
            "opening_float": "2000.00",
            "business_date": str(TODAY),
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="shift-1",
    ).json()


def test_the_payment_buttons_can_be_listed(client, modes):
    listed = client.get("/api/v1/payments/modes/").json()
    codes = {mode["code"] for mode in listed["results"]}

    assert "cash" in codes
    assert listed["results"][0]["sort_order"] <= listed["results"][-1]["sort_order"]


def test_a_bill_is_settled_in_cash(client, paracetamol, branch, counter, modes, shift):
    issued = bill_of_80(client, branch, counter, paracetamol)

    response = client.post(
        f"/api/v1/sales/invoices/{issued['id']}/payments/",
        {
            "tenders": [{"mode": str(modes["cash"].pk), "amount": "80.00"}],
            "shift": shift["id"],
            "tendered_cash": "100.00",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="pay-1",
    )
    assert response.status_code == 201
    payment = response.json()[0]
    assert payment["change_amount"] == "20.00"

    invoice = client.get(f"/api/v1/sales/invoices/{issued['id']}/").json()
    assert invoice["amount_outstanding"] == "0.00"


def test_a_bill_can_be_split_across_two_methods(client, paracetamol, branch, counter, modes, shift):
    issued = bill_of_80(client, branch, counter, paracetamol)

    response = client.post(
        f"/api/v1/sales/invoices/{issued['id']}/payments/",
        {
            "tenders": [
                {"mode": str(modes["cash"].pk), "amount": "30.00"},
                {"mode": str(modes["fonepay"].pk), "amount": "50.00", "reference": "FP-1"},
            ],
            "shift": shift["id"],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="pay-2",
    )
    assert response.status_code == 201
    assert len(response.json()) == 2


def test_paying_twice_over_is_refused(client, paracetamol, branch, counter, modes, shift):
    issued = bill_of_80(client, branch, counter, paracetamol)
    body = {
        "tenders": [{"mode": str(modes["cash"].pk), "amount": "80.00"}],
        "shift": shift["id"],
    }
    client.post(
        f"/api/v1/sales/invoices/{issued['id']}/payments/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY="pay-3",
    )
    response = client.post(
        f"/api/v1/sales/invoices/{issued['id']}/payments/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY="pay-4",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PAYMENT_EXCEEDS_WHAT_IS_DUE"


def test_a_retried_payment_takes_the_money_once(client, paracetamol, branch, counter, modes, shift):
    issued = bill_of_80(client, branch, counter, paracetamol)
    body = {
        "tenders": [{"mode": str(modes["cash"].pk), "amount": "80.00"}],
        "shift": shift["id"],
    }
    first = client.post(
        f"/api/v1/sales/invoices/{issued['id']}/payments/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY="pay-same",
    )
    second = client.post(
        f"/api/v1/sales/invoices/{issued['id']}/payments/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY="pay-same",
    )

    assert first.json() == second.json()
    assert second["Idempotent-Replay"] == "true"


# --------------------------------------------------------------------------- the till
def test_a_till_opens_and_reports_what_it_should_hold(
    client, paracetamol, branch, counter, modes, shift
):
    issued = bill_of_80(client, branch, counter, paracetamol)
    client.post(
        f"/api/v1/sales/invoices/{issued['id']}/payments/",
        {"tenders": [{"mode": str(modes["cash"].pk), "amount": "80.00"}], "shift": shift["id"]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="pay-5",
    )

    summary = client.get(f"/api/v1/payments/shifts/{shift['id']}/summary/").json()
    assert summary["opening_float"] == "2000.00"
    assert summary["cash_received"] == "80.00"
    assert summary["expected_cash"] == "2080.00"
    assert summary["by_mode"]["cash"] == "80.00"


def test_the_drawer_is_counted_in_notes_and_coins(client, shift):
    response = client.post(
        f"/api/v1/payments/shifts/{shift['id']}/close/",
        {"counts": [{"value": 1000, "count": 2}]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="close-1",
    )
    assert response.status_code == 200
    closed = response.json()
    assert closed["status"] == ShiftStatus.CLOSED
    assert closed["counted_cash"] == "2000.00"
    assert closed["variance"] == "0.00"


def test_a_short_drawer_will_not_close_without_an_explanation(client, shift):
    response = client.post(
        f"/api/v1/payments/shifts/{shift['id']}/close/",
        {"counts": [{"value": 1000, "count": 1}]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="close-2",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VARIANCE_NEEDS_AN_EXPLANATION"


def test_money_out_of_the_till_needs_a_witness(client, shift):
    response = client.post(
        f"/api/v1/payments/shifts/{shift['id']}/cash/",
        {"kind": "petty_expense", "amount": "-600.00", "reason": "Taxi to the wholesaler"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="cash-1",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CASH_OUT_NEEDS_A_WITNESS"


def test_a_witnessed_payout_comes_off_the_expected_cash(client, shift):
    client.post(
        f"/api/v1/payments/shifts/{shift['id']}/cash/",
        {
            "kind": "petty_expense",
            "amount": "-600.00",
            "reason": "Taxi to the wholesaler",
            "witness_name": "Hari Thapa",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="cash-2",
    )
    summary = client.get(f"/api/v1/payments/shifts/{shift['id']}/summary/").json()
    assert summary["expected_cash"] == "1400.00"


def test_a_cashier_cannot_sign_off_their_own_count(client, shift, provisioned):
    """One person, however many buttons they press."""
    client.post(
        f"/api/v1/payments/shifts/{shift['id']}/close/",
        {"counts": [{"value": 1000, "count": 2}]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="close-3",
    )
    assistant = member_of(provisioned, email="assist@example.com", role_code="assistant_pharmacist")
    api = api_for(assistant, provisioned)

    response = api.post(f"/api/v1/payments/shifts/{shift['id']}/approve/")
    assert response.status_code == 403


def test_a_supervisor_signs_it_off(client, shift, provisioned):
    client.post(
        f"/api/v1/payments/shifts/{shift['id']}/close/",
        {"counts": [{"value": 1000, "count": 2}]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="close-4",
    )
    boss = member_of(provisioned, email="boss@example.com", role_code="pharmacist_in_charge")
    api = api_for(boss, provisioned)

    response = api.post(f"/api/v1/payments/shifts/{shift['id']}/approve/")
    assert response.status_code == 200
    assert response.json()["approved_at"]


# --------------------------------------------------------------------------- the ledger
def test_a_customer_statement_reads_back(client, paracetamol, branch, counter, modes, shift):
    from core.parties.models import Party

    clinic = Party.objects.create(
        name="Shanti Clinic", is_customer=True, credit_limit=Decimal("5000"), credit_days=30
    )
    stock_up(paracetamol, branch, counter)
    draft = client.post(
        "/api/v1/sales/invoices/",
        {
            "branch": str(branch.pk),
            "location": str(counter.pk),
            "invoice_date": str(TODAY),
            "customer": str(clinic.pk),
        },
        format="json",
    ).json()
    client.post(
        f"/api/v1/sales/invoices/{draft['id']}/lines/",
        {"item": str(paracetamol.pk), "quantity": "4"},
        format="json",
    )
    issued = client.post(
        f"/api/v1/sales/invoices/{draft['id']}/issue/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="issue-clinic",
    ).json()

    on_account = client.post(
        f"/api/v1/sales/invoices/{issued['id']}/payments/",
        {"tenders": [{"mode": str(modes["credit"].pk), "amount": "80.00"}]},
        format="json",
        HTTP_IDEMPOTENCY_KEY="on-account",
    )
    assert on_account.status_code == 201, on_account.json()

    statement = client.get(
        f"/api/v1/customers/ledger/{clinic.pk}/statement/",
        {"date_from": str(TODAY), "date_to": str(TODAY)},
    ).json()

    assert statement["outstanding"] == "80.00"
    assert [line["kind"] for line in statement["lines"]] == ["invoice"]
    assert statement["lines"][0]["debit"] == "80.00"
    assert statement["lines"][0]["balance"] == "80.00"

    # Ageing is always "as of today", and the synthetic business date is years ago, so the whole
    # balance sits in the oldest bucket. What matters is that it is all accounted for somewhere.
    assert sum(Decimal(value) for value in statement["ageing"].values()) == Decimal("80.00")
    assert statement["ageing"]["90+"] == "80.00"
