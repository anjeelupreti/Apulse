import pytest
from rest_framework.test import APIClient

from kernel.identity.models import User

pytestmark = pytest.mark.django_db


def test_me_requires_authentication_and_uses_envelope():
    response = APIClient().get("/api/v1/me/")
    assert response.status_code == 403  # 401 once token auth is added in M2.2
    assert response.json()["error"]["code"] == "AUTH_NOT_AUTHENTICATED"


def test_me_returns_current_user_without_sensitive_fields():
    user = User.objects.create_user("maya@example.com", "maya-pass-123", full_name="Maya")
    client = APIClient()
    client.force_authenticate(user)
    body = client.get("/api/v1/me/").json()
    assert body["id"] == str(user.pk)
    assert body["email"] == "maya@example.com"
    assert "password" not in body
    assert "is_superuser" not in body
