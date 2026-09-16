from kernel.rbac import registry, system_roles


def test_every_permission_named_in_a_built_in_role_actually_exists():
    """Catches a typo in a role definition, which would otherwise grant nothing, silently."""
    unknown: dict[str, list[str]] = {}
    for role in system_roles.SYSTEM_ROLES:
        if isinstance(role.permissions, tuple):
            missing = [code for code in role.permissions if not registry.exists(code)]
            if missing:
                unknown[role.code] = missing
    assert not unknown, f"Unknown permissions in built-in roles: {unknown}"


def test_owner_can_do_everything():
    assert system_roles.BY_CODE[system_roles.OWNER].resolve() == registry.all_codes()


def test_auditor_and_inspector_can_only_read():
    """A new module must not be able to hand an inspector write access by accident."""
    for code in (system_roles.AUDITOR, system_roles.DDA_INSPECTOR):
        resolved = system_roles.BY_CODE[code].resolve()
        assert resolved == registry.read_only_codes()
        assert all(registry.get(permission).is_read_only for permission in resolved)


def test_roles_are_bilingual_and_described():
    for role in system_roles.SYSTEM_ROLES:
        assert role.name_en.strip()
        assert role.name_ne.strip()
        assert role.description.strip()


def test_role_codes_are_unique():
    codes = [role.code for role in system_roles.SYSTEM_ROLES]
    assert len(codes) == len(set(codes))


def test_counter_staff_cannot_change_the_organisation():
    resolved = system_roles.BY_CODE[system_roles.COUNTER_STAFF].resolve()
    assert "tenancy.branch.manage" not in resolved
    assert "rbac.assignment.manage" not in resolved
