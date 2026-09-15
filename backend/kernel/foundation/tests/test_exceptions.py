import pytest
from rest_framework.test import APIClient

# django_db: ATOMIC_REQUESTS opens a transaction around every API request.
pytestmark = [pytest.mark.urls("kernel.foundation.tests.urls"), pytest.mark.django_db]


@pytest.fixture
def client():
    return APIClient()


def test_domain_error_renders_envelope_with_nepali_message(client):
    response = client.get("/domain-error/", HTTP_X_REQUEST_ID="req-12345678")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "VERSION_CONFLICT"
    assert error["message_ne"]
    assert error["details"] == [{"field": "version", "code": "stale"}]
    assert error["request_id"] == "req-12345678"


def test_validation_errors_are_flattened_with_field_paths(client):
    response = client.post(
        "/validation/", {"name": "too-long-name", "lines": [{"qty": 2}, {"qty": 0}]}, format="json"
    )
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    fields = {detail["field"]: detail["code"] for detail in error["details"]}
    assert fields == {"name": "max_length", "lines[1].qty": "min_value"}


def test_malformed_json_is_reported(client):
    response = client.post("/validation/", "{not json", content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MALFORMED_REQUEST"


def test_django_http404_is_mapped(client):
    response = client.get("/not-found/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_method_not_allowed_is_mapped(client):
    response = client.delete("/domain-error/")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_unhandled_exception_returns_generic_envelope_without_leaking(client):
    response = client.get("/crash/")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "SERVER_ERROR"
    assert "boom" not in response.content.decode()
