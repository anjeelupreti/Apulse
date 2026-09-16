"""Sign-in, two-factor enrolment and the surrounding security rules."""

from dataclasses import dataclass

import structlog
from django.contrib.auth import login as django_login
from django.core import signing
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from kernel.tenancy.models import Tenant, TenantMembership
from shared.errors import DomainError, ErrorCode, codes

from . import errors, lockout
from .backends import EmailOrPhoneBackend, find_user_by_identifier
from .models import LoginAttempt, LoginOutcome, RecoveryCode, TwoFactorDevice, User
from .two_factor import (
    check_recovery_code,
    generate_recovery_codes,
    generate_secret,
    hash_recovery_code,
    matched_timestep,
    provisioning_uri,
)

logger = structlog.get_logger(__name__)

CHALLENGE_SALT = "identity.two-factor-challenge"
CHALLENGE_MAX_AGE_SECONDS = 300
AUTH_BACKEND = "kernel.identity.backends.EmailOrPhoneBackend"


class AuthenticationFailedError(DomainError):
    """Sign-in refused. Rendered by the API as the standard error envelope."""

    def __init__(self, error: ErrorCode) -> None:
        super().__init__(error)


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: User
    requires_two_factor: bool
    challenge_token: str | None = None
    used_recovery_code: bool = False


# --------------------------------------------------------------------------- recording
def record_attempt(
    request: HttpRequest,
    *,
    identifier: str,
    outcome: str,
    user: User | None = None,
) -> None:
    tenant = getattr(request, "tenant", None)
    LoginAttempt.objects.create(
        user=user,
        identifier=identifier[:254],
        tenant_slug=tenant.slug if isinstance(tenant, Tenant) else "",
        outcome=outcome,
        ip_address=lockout.client_ip(request) or None,
        user_agent=request.headers.get("User-Agent", "")[:400],
    )


# --------------------------------------------------------------------------- sign-in
def authenticate_credentials(
    request: HttpRequest, *, identifier: str, password: str
) -> LoginResult:
    """Verify a password and either sign the user in or demand a second factor."""
    ip = lockout.client_ip(request)

    if lockout.is_locked(identifier, ip):
        record_attempt(request, identifier=identifier, outcome=LoginOutcome.LOCKED_OUT)
        raise AuthenticationFailedError(errors.AUTH_TOO_MANY_ATTEMPTS)

    user = EmailOrPhoneBackend().authenticate(request, username=identifier, password=password)
    if user is None:
        lockout.record_failure(identifier, ip)
        # Deliberately generic: never say whether the account exists or the password was wrong.
        known = find_user_by_identifier(identifier)
        outcome = (
            LoginOutcome.DISABLED
            if known is not None and not known.is_active
            else LoginOutcome.INVALID_CREDENTIALS
        )
        record_attempt(request, identifier=identifier, outcome=outcome, user=known)
        raise AuthenticationFailedError(codes.AUTH_FAILED)

    _require_tenant_membership(request, user=user, identifier=identifier)

    device = TwoFactorDevice.objects.filter(user=user, confirmed_at__isnull=False).first()
    if device is not None:
        record_attempt(
            request, identifier=identifier, outcome=LoginOutcome.TWO_FACTOR_REQUIRED, user=user
        )
        return LoginResult(
            user=user, requires_two_factor=True, challenge_token=_issue_challenge(user)
        )

    lockout.reset(identifier, ip)
    _establish_session(request, user)
    record_attempt(request, identifier=identifier, outcome=LoginOutcome.SUCCESS, user=user)
    return LoginResult(user=user, requires_two_factor=False)


def complete_two_factor(request: HttpRequest, *, challenge_token: str, code: str) -> LoginResult:
    """Finish a sign-in that was paused for a verification code."""
    user = _consume_challenge(challenge_token)
    identifier = user.email or user.phone or str(user.pk)
    ip = lockout.client_ip(request)

    if lockout.is_locked(identifier, ip):
        record_attempt(request, identifier=identifier, outcome=LoginOutcome.LOCKED_OUT, user=user)
        raise AuthenticationFailedError(errors.AUTH_TOO_MANY_ATTEMPTS)

    device = TwoFactorDevice.objects.filter(user=user, confirmed_at__isnull=False).first()
    if device is None:
        raise AuthenticationFailedError(errors.AUTH_CHALLENGE_INVALID)

    used_recovery_code = False
    step = matched_timestep(device.secret, code)
    if step is not None and step != device.last_used_timestep:
        device.last_used_timestep = step
        device.save(update_fields=["last_used_timestep", "updated_at"])
    elif _consume_recovery_code(user, code):
        used_recovery_code = True
    else:
        lockout.record_failure(identifier, ip)
        record_attempt(
            request, identifier=identifier, outcome=LoginOutcome.TWO_FACTOR_FAILED, user=user
        )
        raise AuthenticationFailedError(errors.AUTH_TWO_FACTOR_INVALID)

    _require_tenant_membership(request, user=user, identifier=identifier)
    lockout.reset(identifier, ip)
    _establish_session(request, user)
    record_attempt(
        request,
        identifier=identifier,
        outcome=LoginOutcome.RECOVERY_CODE_USED if used_recovery_code else LoginOutcome.SUCCESS,
        user=user,
    )
    return LoginResult(user=user, requires_two_factor=False, used_recovery_code=used_recovery_code)


def _establish_session(request: HttpRequest, user: User) -> None:
    django_login(request, user, backend=AUTH_BACKEND)
    logger.info("login_succeeded", user_id=str(user.pk))


def _require_tenant_membership(request: HttpRequest, *, user: User, identifier: str) -> None:
    """On a tenant's own address, only its members may sign in.

    Without this, valid credentials for any pharmacy would open a session on every other
    pharmacy's subdomain.
    """
    tenant = getattr(request, "tenant", None)
    if not isinstance(tenant, Tenant):
        return
    is_member = TenantMembership.objects.filter(
        tenant=tenant, user=user, status=TenantMembership.Status.ACTIVE
    ).exists()
    if not is_member:
        record_attempt(
            request, identifier=identifier, outcome=LoginOutcome.NO_TENANT_ACCESS, user=user
        )
        raise AuthenticationFailedError(errors.AUTH_NO_TENANT_ACCESS)


# --------------------------------------------------------------------------- challenge token
def _issue_challenge(user: User) -> str:
    """Short-lived proof that the password step already succeeded."""
    return signing.dumps({"user_id": str(user.pk)}, salt=CHALLENGE_SALT)


def _consume_challenge(token: str) -> User:
    try:
        payload = signing.loads(token, salt=CHALLENGE_SALT, max_age=CHALLENGE_MAX_AGE_SECONDS)
    except signing.BadSignature as exc:
        raise AuthenticationFailedError(errors.AUTH_CHALLENGE_INVALID) from exc

    user = User.objects.filter(pk=payload.get("user_id"), is_active=True).first()
    if user is None:
        raise AuthenticationFailedError(errors.AUTH_CHALLENGE_INVALID)
    return user


def _consume_recovery_code(user: User, code: str) -> bool:
    for recovery in RecoveryCode.objects.filter(user=user, used_at__isnull=True):
        if check_recovery_code(code, recovery.code_hash):
            recovery.used_at = timezone.now()
            recovery.save(update_fields=["used_at", "updated_at"])
            logger.warning("recovery_code_used", user_id=str(user.pk))
            return True
    return False


# --------------------------------------------------------------------------- enrolment
def start_two_factor_setup(user: User) -> tuple[TwoFactorDevice, str]:
    """Create (or restart) an unconfirmed enrolment and return the provisioning URI."""
    device = TwoFactorDevice.objects.filter(user=user).first()
    if device is not None and device.is_confirmed:
        raise AuthenticationFailedError(errors.AUTH_TWO_FACTOR_ALREADY_ENABLED)

    secret = generate_secret()
    if device is None:
        device = TwoFactorDevice.objects.create(user=user, secret=secret)
    else:
        device.secret = secret
        device.last_used_timestep = None
        device.save(update_fields=["secret", "last_used_timestep", "updated_at"])

    account_name = user.email or user.phone or str(user.pk)
    return device, provisioning_uri(secret=secret, account_name=account_name)


@transaction.atomic
def confirm_two_factor(user: User, *, code: str) -> list[str]:
    """Confirm enrolment with a live code and issue recovery codes (returned once, then hashed)."""
    device = TwoFactorDevice.objects.filter(user=user, confirmed_at__isnull=True).first()
    if device is None:
        raise AuthenticationFailedError(errors.AUTH_TWO_FACTOR_NOT_SET_UP)

    step = matched_timestep(device.secret, code)
    if step is None:
        raise AuthenticationFailedError(errors.AUTH_TWO_FACTOR_INVALID)

    device.confirmed_at = timezone.now()
    device.last_used_timestep = step
    device.save(update_fields=["confirmed_at", "last_used_timestep", "updated_at"])
    logger.info("two_factor_enabled", user_id=str(user.pk))
    return regenerate_recovery_codes(user)


@transaction.atomic
def regenerate_recovery_codes(user: User) -> list[str]:
    RecoveryCode.objects.filter(user=user).delete()
    codes = generate_recovery_codes()
    RecoveryCode.objects.bulk_create(
        [RecoveryCode(user=user, code_hash=hash_recovery_code(code)) for code in codes]
    )
    return codes


@transaction.atomic
def disable_two_factor(user: User) -> None:
    TwoFactorDevice.objects.filter(user=user).delete()
    RecoveryCode.objects.filter(user=user).delete()
    logger.warning("two_factor_disabled", user_id=str(user.pk))
