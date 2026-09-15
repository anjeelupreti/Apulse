import pytest

from kernel.foundation import health


def test_healthz_does_not_need_database(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_reports_build_identity(client):
    body = client.get("/version").json()
    assert set(body) == {"version", "git_sha", "build_time", "environment"}
    assert body["environment"] == "test"


@pytest.mark.django_db
def test_readyz_is_ok_when_dependencies_are_up(client):
    response = client.get("/readyz")
    body = response.json()
    assert response.status_code == 200, body
    assert set(body["checks"]) == {"database", "migrations", "redis"}


@pytest.mark.django_db
def test_readyz_fails_and_hides_details_when_a_check_breaks(client, monkeypatch):
    def broken() -> None:
        raise ConnectionError("redis://secret-host:6379 refused")

    monkeypatch.setitem(health.READINESS_CHECKS, "redis", broken)
    response = client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "fail"
    assert body["checks"]["redis"]["error"] == "ConnectionError"
    assert "secret-host" not in response.content.decode()


def test_health_endpoints_reject_non_get(client):
    assert client.post("/healthz").status_code == 405
