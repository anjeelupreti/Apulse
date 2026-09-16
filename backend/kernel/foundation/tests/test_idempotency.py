"""A retried request must not bill the customer twice."""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from kernel.foundation.api import idempotency
from kernel.foundation.tests import api_urls

pytestmark = [pytest.mark.urls("kernel.foundation.tests.api_urls"), pytest.mark.django_db]


@pytest.fixture(autouse=True)
def clean():
    cache.clear()
    api_urls.reset()
    yield
    cache.clear()


@pytest.fixture
def client():
    return APIClient()


def post(client, path="/create/", key=None, body=None):
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
    return client.post(path, body or {"amount": "80.00"}, format="json", **headers)


# --------------------------------------------------------------------------- the point of it
def test_the_same_key_twice_does_the_work_once(client):
    """The connection stalled and the till retried. There must be one bill, not two."""
    first = post(client, key="till-1-0001")
    second = post(client, key="till-1-0001")

    assert first.status_code == second.status_code == 201
    assert api_urls.CALLS["create"] == 1
    assert first.json() == second.json()


def test_a_replay_says_that_it_is_one(client):
    post(client, key="till-1-0001")
    replayed = post(client, key="till-1-0001")

    assert replayed[idempotency.REPLAY_HEADER] == "true"


def test_different_keys_are_different_requests(client):
    post(client, key="till-1-0001")
    post(client, key="till-1-0002")

    assert api_urls.CALLS["create"] == 2


def test_no_key_means_no_protection(client):
    """Deliberate: a caller that does not ask for it gets the plain behaviour."""
    post(client)
    post(client)

    assert api_urls.CALLS["create"] == 2


def test_an_endpoint_can_insist_on_a_key(client):
    response = post(client, path="/required/")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


# --------------------------------------------------------------------------- the awkward cases
def test_the_same_key_with_different_content_is_refused(client):
    """A client bug. Returning the old answer would hide it and look like nothing changed."""
    post(client, key="till-1-0001", body={"amount": "80.00"})
    response = post(client, key="till-1-0001", body={"amount": "800.00"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_a_retry_arriving_mid_flight_is_told_to_wait(client):
    """Two concurrent bills is the exact failure this exists to prevent."""
    entry = idempotency.cache_key(tenant_id=None, user_id=None, path="/create/", key="till-1-0001")
    cache.set(entry, "__in_flight__", timeout=90)

    response = post(client, key="till-1-0001")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENT_REQUEST_IN_FLIGHT"


def test_a_failure_is_not_remembered(client):
    """The counter fixes the prescription and presses again; replaying the refusal would stop it."""
    first = post(client, path="/failing/", key="till-1-0009")
    assert first.status_code == 400

    second = post(client, path="/failing/", key="till-1-0009")
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_failure_releases_the_key_for_a_genuine_retry(client):
    post(client, path="/failing/", key="till-1-0009")
    entry = idempotency.cache_key(tenant_id=None, user_id=None, path="/failing/", key="till-1-0009")
    assert cache.get(entry) is None


def test_the_same_key_on_another_endpoint_is_another_operation(client):
    post(client, path="/create/", key="shared")
    post(client, path="/required/", key="shared")

    assert api_urls.CALLS == {"create": 1, "required": 1}


def test_one_users_key_cannot_replay_anothers_answer():
    """Scoped to the user, because otherwise it is a data leak dressed up as a convenience."""
    first = idempotency.cache_key(tenant_id="t1", user_id="user-a", path="/create/", key="k")
    second = idempotency.cache_key(tenant_id="t1", user_id="user-b", path="/create/", key="k")
    assert first != second


def test_one_tenants_key_cannot_replay_anothers_answer():
    first = idempotency.cache_key(tenant_id="t1", user_id="u", path="/create/", key="k")
    second = idempotency.cache_key(tenant_id="t2", user_id="u", path="/create/", key="k")
    assert first != second


def test_the_fingerprint_ignores_key_order():
    """The same request serialised differently is still the same request."""
    assert idempotency.fingerprint({"a": 1, "b": 2}) == idempotency.fingerprint({"b": 2, "a": 1})
