import pytest

from kernel.entitlements import manifest
from kernel.entitlements.manifest import (
    DependencyError,
    FeatureKind,
    FeatureSpec,
    ModuleManifest,
    register,
)


def a_module(code: str, depends_on: tuple[str, ...] = ()) -> ModuleManifest:
    return ModuleManifest(
        code=code,
        name_en=code.title(),
        name_ne=code,
        description=f"{code} module",
        depends_on=depends_on,
    )


def test_the_platform_module_is_declared_and_always_on():
    platform = manifest.get("platform")
    assert platform.is_core
    assert "platform" in manifest.core_codes()


def test_declared_features_are_discoverable():
    branches = manifest.find_feature("platform.branches")
    assert branches.kind == FeatureKind.LIMIT
    assert branches.unit == "branches"
    assert branches.default is None  # unlimited until a plan says otherwise


def test_every_declared_feature_is_bilingual():
    for spec in manifest.feature_specs().values():
        assert spec.name_en.strip()
        assert spec.name_ne.strip()


@pytest.mark.parametrize("bad_code", ["Platform", "with-hyphen", "with.dot", "9lives"])
def test_module_codes_are_checked(bad_code, temporary_manifests):
    with pytest.raises(ValueError, match="lower_snake_case"):
        register(a_module(bad_code))


def test_a_module_cannot_be_registered_twice(temporary_manifests):
    with pytest.raises(ValueError, match="already registered"):
        register(a_module("platform"))


def test_a_feature_must_belong_to_its_module(temporary_manifests):
    with pytest.raises(ValueError, match="does not belong to module"):
        register(
            ModuleManifest(
                code="pharmacy",
                name_en="Pharmacy",
                name_ne="फार्मेसी",
                description="",
                features=(FeatureSpec(code="wholesale.routes", name_en="Routes", name_ne="मार्ग"),),
            )
        )


def test_a_feature_needs_both_languages(temporary_manifests):
    with pytest.raises(ValueError, match="English and Nepali"):
        register(
            ModuleManifest(
                code="pharmacy",
                name_en="Pharmacy",
                name_ne="फार्मेसी",
                description="",
                features=(FeatureSpec(code="pharmacy.pos", name_en="POS", name_ne=" "),),
            )
        )


def test_a_missing_dependency_is_caught_at_startup(temporary_manifests):
    """Better a failed deploy than a customer discovering it at install time."""
    register(a_module("wholesale", depends_on=("does_not_exist",)))
    with pytest.raises(DependencyError, match="not installed"):
        manifest.validate_dependencies()


def test_modules_depending_on_each_other_in_a_circle_are_caught(temporary_manifests):
    manifest._registry.clear()
    register(a_module("first", depends_on=("second",)))
    register(a_module("second", depends_on=("first",)))
    with pytest.raises(DependencyError, match="circle"):
        manifest.validate_dependencies()


def test_install_order_puts_dependencies_first(temporary_manifests):
    manifest._registry.clear()
    register(a_module("base"))
    register(a_module("middle", depends_on=("base",)))
    register(a_module("top", depends_on=("middle",)))
    assert manifest.resolve_install_order("top") == ("base", "middle", "top")


def test_the_declared_manifests_are_consistent():
    """Guards the real manifests, not a fixture's."""
    manifest.validate_dependencies()
