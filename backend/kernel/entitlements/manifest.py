"""Module manifests: what a sellable unit is, what it contains and what it needs."""

import re
from dataclasses import dataclass, field
from enum import StrEnum

MODULE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
FEATURE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


class FeatureKind(StrEnum):
    BOOLEAN = "boolean"
    #: A ceiling that holds at any moment — branches, users, devices.
    LIMIT = "limit"
    #: An allowance consumed over a period and reset — SMS messages per month.
    QUOTA = "quota"


class ModuleStatus(StrEnum):
    ALPHA = "alpha"
    BETA = "beta"
    GA = "ga"
    DEPRECATED = "deprecated"


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    code: str
    name_en: str
    name_ne: str
    kind: FeatureKind = FeatureKind.BOOLEAN
    unit: str = ""
    #: What applies with no grant: off for a switch, unlimited (None) for a ceiling. The kernel
    #: sells nothing, so restrictions arrive from a plan rather than being assumed here.
    default: bool | int | None = None
    description: str = ""

    @property
    def module_code(self) -> str:
        return self.code.split(".", 1)[0]


@dataclass(frozen=True, slots=True)
class ModuleManifest:
    code: str
    name_en: str
    name_ne: str
    description: str
    version: str = "1.0.0"
    depends_on: tuple[str, ...] = ()
    features: tuple[FeatureSpec, ...] = ()
    #: Always installed and never disabled — the platform itself.
    is_core: bool = False
    status: ModuleStatus = ModuleStatus.GA
    permissions: tuple[str, ...] = field(default_factory=tuple)


_registry: dict[str, ModuleManifest] = {}


def register(manifest: ModuleManifest) -> ModuleManifest:
    if not MODULE_CODE_PATTERN.fullmatch(manifest.code):
        raise ValueError(f"Module code must be lower_snake_case: {manifest.code!r}")
    if manifest.code in _registry:
        raise ValueError(f"Module already registered: {manifest.code}")
    for feature in manifest.features:
        if not FEATURE_CODE_PATTERN.fullmatch(feature.code):
            raise ValueError(f"Feature code must be '<module>.<feature>': {feature.code!r}")
        if feature.module_code != manifest.code:
            raise ValueError(
                f"Feature {feature.code!r} does not belong to module {manifest.code!r}"
            )
        if not feature.name_en.strip() or not feature.name_ne.strip():
            raise ValueError(f"Feature {feature.code} needs both English and Nepali names")
    _registry[manifest.code] = manifest
    return manifest


def get(code: str) -> ModuleManifest:
    try:
        return _registry[code]
    except KeyError:
        raise LookupError(f"Unregistered module: {code}") from None


def exists(code: str) -> bool:
    return code in _registry


def all_manifests() -> tuple[ModuleManifest, ...]:
    return tuple(_registry.values())


def core_codes() -> tuple[str, ...]:
    return tuple(code for code, manifest in _registry.items() if manifest.is_core)


def feature_specs() -> dict[str, FeatureSpec]:
    return {
        feature.code: feature for manifest in _registry.values() for feature in manifest.features
    }


def find_feature(code: str) -> FeatureSpec:
    try:
        return feature_specs()[code]
    except KeyError:
        raise LookupError(f"Unregistered feature: {code}") from None


class DependencyError(ValueError):
    """A module depends on something missing, or modules depend on each other in a circle."""


def validate_dependencies() -> None:
    """Fail at startup rather than at install time, when it would be a customer's problem."""
    for manifest in _registry.values():
        for dependency in manifest.depends_on:
            if dependency not in _registry:
                raise DependencyError(
                    f"Module {manifest.code!r} depends on {dependency!r}, which is not installed"
                )
    _detect_cycles()


def _detect_cycles() -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(code: str, trail: tuple[str, ...]) -> None:
        if code in visited:
            return
        if code in visiting:
            cycle = " -> ".join([*trail, code])
            raise DependencyError(f"Modules depend on each other in a circle: {cycle}")
        visiting.add(code)
        for dependency in _registry[code].depends_on:
            walk(dependency, (*trail, code))
        visiting.discard(code)
        visited.add(code)

    for code in _registry:
        walk(code, ())


def resolve_install_order(code: str) -> tuple[str, ...]:
    """A module and everything it needs, dependencies first."""
    order: list[str] = []

    def walk(current: str) -> None:
        for dependency in get(current).depends_on:
            walk(dependency)
        if current not in order:
            order.append(current)

    walk(code)
    return tuple(order)


def autodiscover() -> None:
    """Import every installed app's `module` module, which is where manifests register."""
    from django.utils.module_loading import autodiscover_modules

    autodiscover_modules("module")
    validate_dependencies()
