"""Two people editing one row: the second one is told, not silently discarded."""

import pytest
from rest_framework.test import APIClient

from kernel.foundation.api import concurrency

pytestmark = [pytest.mark.urls("kernel.foundation.tests.api_urls"), pytest.mark.django_db]


@pytest.fixture
def client():
    return APIClient()


# --------------------------------------------------------------------------- the check
def test_editing_the_current_version_is_allowed(client):
    response = client.patch("/versioned/", {"version": 3}, format="json")
    assert response.status_code == 200
    assert response.json()["version"] == 4


def test_editing_a_stale_version_is_refused(client):
    """Last-write-wins would lose the other person's change with no trace and no warning."""
    response = client.patch("/versioned/", {"version": 2}, format="json")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "VERSION_CONFLICT"
    assert "version 3" in error["message"]


def test_saying_nothing_about_the_version_is_refused(client):
    response = client.patch("/versioned/", {}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VERSION_REQUIRED"


def test_a_view_may_treat_the_version_as_optional(client):
    response = client.patch("/optional-version/", {}, format="json")
    assert response.status_code == 200


# --------------------------------------------------------------------------- how it is sent
def test_the_version_can_come_from_an_if_match_header(client):
    """What a generated HTTP client sends, as opposed to what a form posts."""
    response = client.patch("/versioned/", {}, format="json", HTTP_IF_MATCH='W/"3"')
    assert response.status_code == 200


def test_a_bare_number_in_if_match_works_too(client):
    response = client.patch("/versioned/", {}, format="json", HTTP_IF_MATCH="3")
    assert response.status_code == 200


def test_a_stale_if_match_is_refused(client):
    response = client.patch("/versioned/", {}, format="json", HTTP_IF_MATCH='W/"1"')
    assert response.status_code == 409


def test_the_response_carries_the_new_etag(client):
    response = client.patch("/versioned/", {"version": 3}, format="json")
    assert response[concurrency.ETAG] == 'W/"4"'


def test_a_body_version_wins_over_a_header(client):
    """The form the person filled in is the more specific statement of intent."""
    response = client.patch("/versioned/", {"version": 1}, format="json", HTTP_IF_MATCH='W/"3"')
    assert response.status_code == 409


# --------------------------------------------------------------------------- the helpers
def test_something_unversioned_is_left_alone():
    class Plain:
        pass

    concurrency.check(Plain(), None, required=True)  # no exception


def test_bumping_moves_it_on():
    class Thing:
        version = 7

    thing = Thing()
    concurrency.bump(thing)
    assert thing.version == 8
