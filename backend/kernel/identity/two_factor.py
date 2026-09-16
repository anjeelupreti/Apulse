"""Time-based one-time passwords and single-use recovery codes."""

import secrets
import time

import pyotp
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password

RECOVERY_CODE_COUNT = 10
_RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no look-alikes: no 0/O, no 1/I/L
TOTP_INTERVAL = 30
# One step of tolerance each way, for clock drift on a counter PC that has never seen NTP.
TOTP_VALID_WINDOW = 1


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(*, secret: str, account_name: str) -> str:
    """The `otpauth://` URI an authenticator app scans."""
    issuer = getattr(settings, "TWO_FACTOR_ISSUER", "NPMS")
    return pyotp.TOTP(secret, interval=TOTP_INTERVAL).provisioning_uri(
        name=account_name, issuer_name=issuer
    )


def current_timestep(at: float | None = None) -> int:
    return int((at if at is not None else time.time()) // TOTP_INTERVAL)


def verify_code(secret: str, code: str) -> bool:
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit():
        return False
    return pyotp.TOTP(secret, interval=TOTP_INTERVAL).verify(code, valid_window=TOTP_VALID_WINDOW)


def matched_timestep(secret: str, code: str) -> int | None:
    """Which time step a code belongs to, so a used code cannot be replayed within its window."""
    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL)
    now = current_timestep()
    for offset in range(-TOTP_VALID_WINDOW, TOTP_VALID_WINDOW + 1):
        step = now + offset
        if secrets.compare_digest(totp.at(step * TOTP_INTERVAL), code.strip()):
            return step
    return None


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Human-transcribable codes, shown once at enrolment."""
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def hash_recovery_code(code: str) -> str:
    return make_password(normalize_recovery_code(code))


def check_recovery_code(code: str, hashed: str) -> bool:
    return check_password(normalize_recovery_code(code), hashed)


def normalize_recovery_code(code: str) -> str:
    return (code or "").strip().upper().replace(" ", "")
