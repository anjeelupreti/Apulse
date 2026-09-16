import pyotp
import pytest
from rest_framework.test import APIClient

from kernel.identity import two_factor
from kernel.identity.models import LoginAttempt, LoginOutcome, RecoveryCode, TwoFactorDevice, User
from kernel.tenancy.models import TenantMembership
from kernel.tenancy.tests.factories import make_tenant

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery-staple"
LOGIN_URL = "/api/v1/auth/login/"
TWO_FACTOR_URL = "/api/v1/auth/login/two-factor/"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user():
    return User.objects.create_user("ram@example.com", PASSWORD, full_name="Ram Sharma")


def login(client, identifier, password=PASSWORD, **extra):
    return client.post(
        LOGIN_URL, {"identifier": identifier, "password": password}, format="json", **extra
    )


def error_body(response) -> dict:
    """The error without `request_id`, which is unique per request by design."""
    return {k: v for k, v in response.json()["error"].items() if k != "request_id"}


def enable_two_factor(user) -> str:
    """Enrol a confirmed authenticator and return its secret."""
    secret = two_factor.generate_secret()
    from django.utils import timezone

    TwoFactorDevice.objects.create(user=user, secret=secret, confirmed_at=timezone.now())
    return secret


# --------------------------------------------------------------------------- password step
def test_login_with_email_succeeds(client, user):
    response = login(client, "ram@example.com")
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["requires_two_factor"] is False
    assert body["user"]["email"] == "ram@example.com"
    assert LoginAttempt.objects.get().outcome == LoginOutcome.SUCCESS


def test_login_with_phone_succeeds(client):
    User.objects.create_user(phone="9812345678", password=PASSWORD, full_name="Sita")
    assert login(client, "9812345678").status_code == 200


def test_session_is_established_so_authenticated_endpoints_work(client, user):
    login(client, "ram@example.com")
    assert client.get("/api/v1/me/").json()["email"] == "ram@example.com"


def test_logout_ends_the_session(client, user):
    login(client, "ram@example.com")
    assert client.post("/api/v1/auth/logout/").status_code == 204
    assert client.get("/api/v1/me/").status_code == 403


# --------------------------------------------------------------------------- no enumeration
def test_wrong_password_and_unknown_account_are_indistinguishable(client, user):
    wrong_password = login(client, "ram@example.com", password="nope")
    unknown_account = login(client, "nobody@example.com", password="nope")

    assert wrong_password.status_code == unknown_account.status_code == 401
    assert error_body(wrong_password) == error_body(unknown_account)


def test_disabled_account_gives_the_same_generic_error(client, user):
    user.is_active = False
    user.save(update_fields=["is_active"])
    response = login(client, "ram@example.com")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_FAILED"
    # The real reason is recorded for support, but never told to the caller.
    assert LoginAttempt.objects.get().outcome == LoginOutcome.DISABLED


def test_failed_attempts_are_recorded_with_context(client, user):
    login(client, "ram@example.com", password="nope", HTTP_USER_AGENT="POS/1.0")
    attempt = LoginAttempt.objects.get()
    assert attempt.outcome == LoginOutcome.INVALID_CREDENTIALS
    assert attempt.identifier == "ram@example.com"
    assert attempt.user_agent == "POS/1.0"


# --------------------------------------------------------------------------- lockout
def test_repeated_failures_lock_further_attempts(client, user, settings):
    settings.LOGIN_MAX_FAILED_ATTEMPTS = 3
    for _ in range(3):
        login(client, "ram@example.com", password="nope")

    # Even the correct password is refused once locked.
    response = login(client, "ram@example.com")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "AUTH_TOO_MANY_ATTEMPTS"


def test_lockout_does_not_reveal_whether_an_account_exists(client, user, settings):
    settings.LOGIN_MAX_FAILED_ATTEMPTS = 2
    for identifier in ("ram@example.com", "ghost@example.com"):
        for _ in range(2):
            login(client, identifier, password="nope")

    real = login(client, "ram@example.com")
    ghost = login(client, "ghost@example.com")
    assert real.status_code == ghost.status_code == 429
    assert error_body(real) == error_body(ghost)


def test_a_successful_sign_in_clears_the_counter(client, user, settings):
    settings.LOGIN_MAX_FAILED_ATTEMPTS = 3
    login(client, "ram@example.com", password="nope")
    login(client, "ram@example.com", password="nope")
    assert login(client, "ram@example.com").status_code == 200

    login(client, "ram@example.com", password="nope")
    assert login(client, "ram@example.com").status_code == 200


# --------------------------------------------------------------------------- tenant membership
def test_members_can_sign_in_on_their_own_tenant_address(client, user):
    provisioned = make_tenant("alpha")
    TenantMembership.objects.create(
        tenant=provisioned.tenant, user=user, status=TenantMembership.Status.ACTIVE
    )
    response = login(client, "ram@example.com", headers={"host": "alpha.testserver"})
    assert response.status_code == 200


def test_valid_credentials_do_not_open_another_pharmacys_account(client, user):
    """Credentials for one pharmacy must not work on a different pharmacy's address."""
    make_tenant("alpha")
    response = login(client, "ram@example.com", headers={"host": "alpha.testserver"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_NO_TENANT_ACCESS"
    assert LoginAttempt.objects.get().outcome == LoginOutcome.NO_TENANT_ACCESS


def test_an_invited_but_not_yet_active_member_cannot_sign_in(client, user):
    provisioned = make_tenant("alpha")
    TenantMembership.objects.create(
        tenant=provisioned.tenant, user=user, status=TenantMembership.Status.INVITED
    )
    response = login(client, "ram@example.com", headers={"host": "alpha.testserver"})
    assert response.status_code == 403


# --------------------------------------------------------------------------- two factor
def test_two_factor_pauses_the_sign_in_without_leaking_the_user(client, user):
    enable_two_factor(user)
    body = login(client, "ram@example.com").json()
    assert body["requires_two_factor"] is True
    assert body["challenge_token"]
    assert body["user"] is None
    # No session yet.
    assert client.get("/api/v1/me/").status_code == 403


def test_two_factor_completes_with_a_valid_code(client, user):
    secret = enable_two_factor(user)
    token = login(client, "ram@example.com").json()["challenge_token"]

    code = pyotp.TOTP(secret, interval=two_factor.TOTP_INTERVAL).now()
    response = client.post(TWO_FACTOR_URL, {"challenge_token": token, "code": code}, format="json")
    assert response.status_code == 200, response.content
    assert response.json()["user"]["email"] == "ram@example.com"
    assert client.get("/api/v1/me/").status_code == 200


def test_the_same_code_cannot_be_used_twice(client, user):
    secret = enable_two_factor(user)
    code = pyotp.TOTP(secret, interval=two_factor.TOTP_INTERVAL).now()

    first = login(client, "ram@example.com").json()["challenge_token"]
    assert (
        client.post(
            TWO_FACTOR_URL, {"challenge_token": first, "code": code}, format="json"
        ).status_code
        == 200
    )

    client.post("/api/v1/auth/logout/")
    second = login(client, "ram@example.com").json()["challenge_token"]
    replay = client.post(TWO_FACTOR_URL, {"challenge_token": second, "code": code}, format="json")
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "AUTH_TWO_FACTOR_INVALID"


def test_a_wrong_code_is_rejected_and_recorded(client, user):
    enable_two_factor(user)
    token = login(client, "ram@example.com").json()["challenge_token"]
    response = client.post(
        TWO_FACTOR_URL, {"challenge_token": token, "code": "000000"}, format="json"
    )
    assert response.status_code == 401
    assert LoginAttempt.objects.filter(outcome=LoginOutcome.TWO_FACTOR_FAILED).exists()


def test_a_tampered_challenge_token_is_refused(client, user):
    enable_two_factor(user)
    response = client.post(
        TWO_FACTOR_URL, {"challenge_token": "not-a-real-token", "code": "123456"}, format="json"
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_CHALLENGE_INVALID"


def test_a_recovery_code_works_once(client, user):
    enable_two_factor(user)
    code = two_factor.generate_recovery_codes(1)[0]
    RecoveryCode.objects.create(user=user, code_hash=two_factor.hash_recovery_code(code))

    token = login(client, "ram@example.com").json()["challenge_token"]
    assert (
        client.post(
            TWO_FACTOR_URL, {"challenge_token": token, "code": code}, format="json"
        ).status_code
        == 200
    )
    assert LoginAttempt.objects.filter(outcome=LoginOutcome.RECOVERY_CODE_USED).exists()

    client.post("/api/v1/auth/logout/")
    token = login(client, "ram@example.com").json()["challenge_token"]
    assert (
        client.post(
            TWO_FACTOR_URL, {"challenge_token": token, "code": code}, format="json"
        ).status_code
        == 401
    )


# --------------------------------------------------------------------------- enrolment
def test_enrolment_flow_issues_recovery_codes_once(client, user):
    login(client, "ram@example.com")

    setup = client.post("/api/v1/auth/two-factor/setup/").json()
    assert setup["provisioning_uri"].startswith("otpauth://")

    code = pyotp.TOTP(setup["secret"], interval=two_factor.TOTP_INTERVAL).now()
    confirm = client.post("/api/v1/auth/two-factor/confirm/", {"code": code}, format="json")
    assert confirm.status_code == 200
    assert len(confirm.json()["recovery_codes"]) == two_factor.RECOVERY_CODE_COUNT
    assert TwoFactorDevice.objects.get(user=user).is_confirmed


def test_confirming_with_a_wrong_code_does_not_enable_it(client, user):
    login(client, "ram@example.com")
    client.post("/api/v1/auth/two-factor/setup/")
    response = client.post("/api/v1/auth/two-factor/confirm/", {"code": "000000"}, format="json")
    assert response.status_code == 401
    assert not TwoFactorDevice.objects.get(user=user).is_confirmed


def test_disabling_two_factor_requires_the_password(client, user):
    enable_two_factor(user)
    token = login(client, "ram@example.com").json()["challenge_token"]
    secret = TwoFactorDevice.objects.get(user=user).secret
    client.post(
        TWO_FACTOR_URL,
        {"challenge_token": token, "code": pyotp.TOTP(secret, interval=30).now()},
        format="json",
    )

    refused = client.post("/api/v1/auth/two-factor/disable/", {"password": "wrong"}, format="json")
    assert refused.status_code == 401
    assert TwoFactorDevice.objects.filter(user=user).exists()

    accepted = client.post(
        "/api/v1/auth/two-factor/disable/", {"password": PASSWORD}, format="json"
    )
    assert accepted.status_code == 204
    assert not TwoFactorDevice.objects.filter(user=user).exists()


def test_regenerating_recovery_codes_invalidates_the_old_ones(client, user):
    enable_two_factor(user)
    old_code = two_factor.generate_recovery_codes(1)[0]
    RecoveryCode.objects.create(user=user, code_hash=two_factor.hash_recovery_code(old_code))

    token = login(client, "ram@example.com").json()["challenge_token"]
    secret = TwoFactorDevice.objects.get(user=user).secret
    client.post(
        TWO_FACTOR_URL,
        {"challenge_token": token, "code": pyotp.TOTP(secret, interval=30).now()},
        format="json",
    )

    response = client.post("/api/v1/auth/recovery-codes/", {"password": PASSWORD}, format="json")
    assert response.status_code == 200
    new_codes = response.json()["recovery_codes"]
    assert old_code not in new_codes
    assert RecoveryCode.objects.filter(user=user).count() == len(new_codes)


# --------------------------------------------------------------------------- context
def test_me_context_reports_tenant_and_branches(client, user):
    provisioned = make_tenant("alpha")
    TenantMembership.objects.create(
        tenant=provisioned.tenant, user=user, status=TenantMembership.Status.ACTIVE
    )
    login(client, "ram@example.com", headers={"host": "alpha.testserver"})

    body = client.get("/api/v1/me/context/", headers={"host": "alpha.testserver"}).json()
    assert body["user"]["email"] == "ram@example.com"
    assert body["tenant"]["slug"] == "alpha"
    assert [branch["code"] for branch in body["branches"]] == ["HQ"]
    assert [m["tenant"]["slug"] for m in body["memberships"]] == ["alpha"]
    assert body["server_time"]


def test_me_context_without_a_tenant_still_lists_memberships(client, user):
    provisioned = make_tenant("alpha")
    TenantMembership.objects.create(
        tenant=provisioned.tenant, user=user, status=TenantMembership.Status.ACTIVE
    )
    login(client, "ram@example.com")

    body = client.get("/api/v1/me/context/").json()
    assert body["tenant"] is None
    assert body["branches"] == []
    assert [m["tenant"]["slug"] for m in body["memberships"]] == ["alpha"]


def test_csrf_endpoint_sets_the_cookie(client):
    response = client.get("/api/v1/auth/csrf/")
    assert response.status_code == 200
    assert "npms_csrftoken" in response.cookies
