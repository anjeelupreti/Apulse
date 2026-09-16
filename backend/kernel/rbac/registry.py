"""The catalogue of every permission the platform understands.

Permissions are code, not data: a role may only grant something that some module actually checks.
Modules declare theirs in a `permissions.py`, which `autodiscover()` imports at startup.
"""

import re
from dataclasses import dataclass, field

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class Permission:
    """One checkable action, named `<module>.<resource>.<action>`."""

    code: str
    label_en: str
    label_ne: str
    description: str = ""
    #: Reading only. Roles such as Auditor and DDA Inspector are built from these automatically,
    #: so a new module cannot accidentally hand an inspector write access.
    is_read_only: bool = False
    #: A professional registration the holder must have, verified and unexpired, for this action —
    #: dispensing a narcotic requires a registered pharmacist, whatever the role says.
    requires_credential: str = field(default="")

    @property
    def module(self) -> str:
        return self.code.split(".", 1)[0]


_registry: dict[str, Permission] = {}


def register(
    code: str,
    label_en: str,
    label_ne: str,
    *,
    description: str = "",
    is_read_only: bool = False,
    requires_credential: str = "",
) -> Permission:
    if not CODE_PATTERN.fullmatch(code):
        raise ValueError(f"Permission code must be '<module>.<resource>.<action>': {code!r}")
    if not label_en.strip() or not label_ne.strip():
        raise ValueError(f"Permission {code} needs both English and Nepali labels")
    if code in _registry:
        raise ValueError(f"Permission already registered: {code}")
    permission = Permission(
        code=code,
        label_en=label_en,
        label_ne=label_ne,
        description=description,
        is_read_only=is_read_only,
        requires_credential=requires_credential,
    )
    _registry[code] = permission
    return permission


def get(code: str) -> Permission:
    try:
        return _registry[code]
    except KeyError:
        raise LookupError(f"Unregistered permission: {code}") from None


def exists(code: str) -> bool:
    return code in _registry


def all_permissions() -> tuple[Permission, ...]:
    return tuple(_registry.values())


def all_codes() -> frozenset[str]:
    return frozenset(_registry)


def read_only_codes() -> frozenset[str]:
    return frozenset(code for code, perm in _registry.items() if perm.is_read_only)


def codes_for_module(module: str) -> frozenset[str]:
    return frozenset(code for code, perm in _registry.items() if perm.module == module)


def autodiscover() -> None:
    """Import every installed app's `permissions` module."""
    from django.utils.module_loading import autodiscover_modules

    autodiscover_modules("permissions")
