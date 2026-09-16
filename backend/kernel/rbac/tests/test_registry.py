import pytest

from kernel.rbac import registry


def test_kernel_permissions_are_registered():
    codes = registry.all_codes()
    assert "tenancy.branch.manage" in codes
    assert "rbac.role.manage" in codes


def test_every_permission_has_both_languages():
    for permission in registry.all_permissions():
        assert permission.label_en.strip()
        assert permission.label_ne.strip()


@pytest.mark.parametrize(
    "bad_code",
    ["nodots", "two.parts", "Upper.Case.Code", "trailing.dot.", "has space.a.b", "a.b.c.d"],
)
def test_code_shape_is_enforced(bad_code):
    with pytest.raises(ValueError, match=r"<module>\.<resource>\.<action>"):
        registry.register(bad_code, "x", "x")


def test_duplicate_registration_is_rejected():
    with pytest.raises(ValueError, match="already registered"):
        registry.register("tenancy.branch.view", "Duplicate", "दोहोरो")


def test_nepali_label_is_required():
    with pytest.raises(ValueError, match="English and Nepali"):
        registry.register("rbac.test.only", "Label", "  ")


def test_unknown_permission_lookup_fails_loudly():
    with pytest.raises(LookupError, match="Unregistered permission"):
        registry.get("nothing.at.all")


def test_read_only_codes_are_a_subset_that_excludes_management_actions():
    read_only = registry.read_only_codes()
    assert "tenancy.branch.view" in read_only
    assert "tenancy.branch.manage" not in read_only
    assert read_only < registry.all_codes()


def test_module_grouping():
    assert registry.codes_for_module("rbac") == {
        "rbac.role.view",
        "rbac.role.manage",
        "rbac.assignment.view",
        "rbac.assignment.manage",
    }
