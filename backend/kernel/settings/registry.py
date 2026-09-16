"""Every setting the code reads, declared in code.

The same arrangement as permissions and document types, and for the same reason: a setting that
exists only as a string typed into `get("pharmcy.rx_required")` is a setting that silently returns
its default for ever, and nobody finds out until an inspector asks why antibiotics were going out
without a prescription.

So a setting is *defined* — with its type, its default, what it is called in both languages, and
which scopes it may be set at — and reading an undeclared key is an error rather than a shrug.

**Scopes.** A value can be set at the platform, the tenant, one legal entity, one branch or one
user, and the narrowest one that has a value wins. Not every setting makes sense everywhere: a
rounding rule belongs to the business, not to whoever happens to be on the till, and letting it be
set per user would mean two cashiers producing different totals for the same basket.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

KEY_SEPARATOR = "."
_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


class SettingKind(StrEnum):
    BOOLEAN = "boolean"
    INTEGER = "integer"
    DECIMAL = "decimal"
    STRING = "string"
    CHOICE = "choice"


class Scope(StrEnum):
    """Where a value can be set. Ordered widest first; resolution walks it backwards.

    `PLATFORM` is the default declared in code. It is part of the chain and appears in a spec's
    allowed scopes, but it has no stored row: see `models.STORABLE_SCOPES` for why.
    """

    PLATFORM = "platform"
    TENANT = "tenant"
    LEGAL_ENTITY = "legal_entity"
    BRANCH = "branch"
    USER = "user"


#: The order the resolver looks in: the narrowest that has a value wins.
RESOLUTION_ORDER: tuple[Scope, ...] = (
    Scope.USER,
    Scope.BRANCH,
    Scope.LEGAL_ENTITY,
    Scope.TENANT,
    Scope.PLATFORM,
)

#: What most settings allow. A setting that names its own scopes is saying something deliberate.
BUSINESS_SCOPES: tuple[Scope, ...] = (
    Scope.PLATFORM,
    Scope.TENANT,
    Scope.LEGAL_ENTITY,
    Scope.BRANCH,
)


class UnknownSettingError(KeyError):
    """A key nobody declared. Almost always a typo, and returning a default would hide it."""


class SettingValueError(ValueError):
    """A value that does not fit what the setting said it accepts."""


@dataclass(frozen=True, slots=True)
class SettingSpec:
    key: str
    kind: SettingKind
    default: Any
    label_en: str
    label_ne: str
    description: str = ""
    scopes: tuple[Scope, ...] = BUSINESS_SCOPES
    choices: tuple[str, ...] = ()
    minimum: Decimal | int | None = None
    maximum: Decimal | int | None = None
    #: A setting whose change alters money already recorded, or what the law allows. Flagged so
    #: the console can ask twice and the trail can be read for them specifically.
    is_sensitive: bool = False
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def module(self) -> str:
        return self.key.split(KEY_SEPARATOR, 1)[0]

    def allows(self, scope: Scope) -> bool:
        return scope in self.scopes


_registry: dict[str, SettingSpec] = {}


def define(
    key: str,
    kind: SettingKind,
    default: Any,
    label_en: str,
    label_ne: str,
    *,
    description: str = "",
    scopes: tuple[Scope, ...] = BUSINESS_SCOPES,
    choices: tuple[str, ...] = (),
    minimum: Decimal | int | None = None,
    maximum: Decimal | int | None = None,
    is_sensitive: bool = False,
    tags: tuple[str, ...] = (),
) -> SettingSpec:
    """Declare a setting. Called at import time from an app's `settings_spec.py`."""
    if not _KEY_PATTERN.fullmatch(key):
        raise ValueError(f"Setting key must be '<module>.<name>' in lower_snake_case: {key!r}")
    if key in _registry:
        raise ValueError(f"Setting already defined: {key}")
    if not label_en.strip() or not label_ne.strip():
        raise ValueError(f"Setting {key} needs both English and Nepali labels")
    if kind is SettingKind.CHOICE and not choices:
        raise ValueError(f"Setting {key} is a choice but lists no options")
    if not scopes:
        raise ValueError(f"Setting {key} must be settable somewhere")

    spec = SettingSpec(
        key=key,
        kind=kind,
        default=default,
        label_en=label_en,
        label_ne=label_ne,
        description=description,
        scopes=tuple(scopes),
        choices=tuple(choices),
        minimum=minimum,
        maximum=maximum,
        is_sensitive=is_sensitive,
        tags=tuple(tags),
    )
    # Validates the default against the spec's own rules, so a setting cannot ship with a default
    # it would refuse if a person typed it.
    coerce(spec, default)
    _registry[key] = spec
    return spec


def get_spec(key: str) -> SettingSpec:
    try:
        return _registry[key]
    except KeyError:
        raise UnknownSettingError(
            f"No setting is declared as {key!r}. Declare it in the app's settings_spec.py."
        ) from None


def exists(key: str) -> bool:
    return key in _registry


def all_specs() -> dict[str, SettingSpec]:
    return dict(_registry)


def for_module(module: str) -> dict[str, SettingSpec]:
    return {key: spec for key, spec in _registry.items() if spec.module == module}


# --------------------------------------------------------------------------- values
def coerce(spec: SettingSpec, value: Any) -> Any:
    """Turn whatever was supplied into the type the setting says it is, or refuse it.

    Strings are accepted for every kind, because a value arriving from a form, a JSON body or an
    imported spreadsheet is a string, and making every caller convert first is how a `"false"`
    ends up being read as true.
    """
    if value is None:
        raise SettingValueError(f"{spec.key} has no value")

    if spec.kind is SettingKind.BOOLEAN:
        return _as_bool(spec, value)
    if spec.kind is SettingKind.INTEGER:
        return _in_range(spec, _as_int(spec, value))
    if spec.kind is SettingKind.DECIMAL:
        return _in_range(spec, _as_decimal(spec, value))
    if spec.kind is SettingKind.CHOICE:
        text = str(value)
        if text not in spec.choices:
            raise SettingValueError(
                f"{spec.key} must be one of {', '.join(spec.choices)}, not {text!r}"
            )
        return text
    return str(value)


def _as_bool(spec: SettingSpec, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    raise SettingValueError(f"{spec.key} is a yes/no setting; {value!r} is neither")


def _as_int(spec: SettingSpec, value: Any) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise SettingValueError(f"{spec.key} must be a whole number, not {value!r}") from None


def _as_decimal(spec: SettingSpec, value: Any) -> Decimal:
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        raise SettingValueError(f"{spec.key} must be a number, not {value!r}") from None


def _in_range(spec: SettingSpec, value: Any) -> Any:
    if spec.minimum is not None and value < spec.minimum:
        raise SettingValueError(f"{spec.key} cannot be below {spec.minimum}")
    if spec.maximum is not None and value > spec.maximum:
        raise SettingValueError(f"{spec.key} cannot be above {spec.maximum}")
    return value


def serialise(spec: SettingSpec, value: Any) -> str:
    """How a value is written to the database: text, so one column holds every kind."""
    coerced = coerce(spec, value)
    if spec.kind is SettingKind.BOOLEAN:
        return "true" if coerced else "false"
    return str(coerced)


def autodiscover() -> None:
    """Import every app's `settings_spec.py`, so declaring one is enough to register it."""
    from django.apps import apps
    from django.utils.module_loading import module_has_submodule

    for config in apps.get_app_configs():
        if module_has_submodule(config.module, "settings_spec"):
            __import__(f"{config.name}.settings_spec")
