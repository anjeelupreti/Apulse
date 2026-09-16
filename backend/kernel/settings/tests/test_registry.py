"""Declaring a setting, and what a declaration refuses. No database needed."""

from decimal import Decimal

import pytest

from kernel.settings.registry import (
    Scope,
    SettingKind,
    SettingValueError,
    UnknownSettingError,
    coerce,
    define,
    exists,
    get_spec,
    serialise,
)


@pytest.fixture
def clean_registry():
    """The registry is module-level, so a test that defines settings puts it back afterwards."""
    from kernel.settings import registry

    saved = dict(registry._registry)
    try:
        yield registry
    finally:
        registry._registry.clear()
        registry._registry.update(saved)


def a_setting(clean_registry, key="testing.thing", **kwargs):
    kwargs.setdefault("kind", SettingKind.BOOLEAN)
    kwargs.setdefault("default", False)
    return define(key, kwargs.pop("kind"), kwargs.pop("default"), "Thing", "कुरा", **kwargs)


# --------------------------------------------------------------------------- declaring
def test_a_setting_has_to_be_declared_before_it_can_be_read():
    """A typo that silently answers "not set" is how a rule quietly stops being enforced."""
    with pytest.raises(UnknownSettingError, match="settings_spec"):
        get_spec("pharmcy.rx_required")


def test_a_key_must_name_its_module(clean_registry):
    for bad in ("Thing", "no_module", "two.dots.here", "9lives.thing"):
        with pytest.raises(ValueError, match="lower_snake_case"):
            a_setting(clean_registry, key=bad)


def test_a_setting_cannot_be_declared_twice(clean_registry):
    a_setting(clean_registry)
    with pytest.raises(ValueError, match="already defined"):
        a_setting(clean_registry)


def test_both_languages_are_required(clean_registry):
    with pytest.raises(ValueError, match="English and Nepali"):
        define("testing.thing", SettingKind.BOOLEAN, False, "Thing", "  ")


def test_a_choice_with_no_options_is_refused(clean_registry):
    with pytest.raises(ValueError, match="lists no options"):
        a_setting(clean_registry, kind=SettingKind.CHOICE, default="a")


def test_a_default_that_breaks_its_own_rules_is_refused(clean_registry):
    """A setting cannot ship with a default it would reject if a person typed it."""
    with pytest.raises(SettingValueError, match="cannot be above"):
        a_setting(clean_registry, kind=SettingKind.INTEGER, default=500, maximum=100)


def test_every_declared_setting_is_bilingual():
    from kernel.settings.registry import all_specs

    for spec in all_specs().values():
        assert spec.label_en.strip(), spec.key
        assert spec.label_ne.strip(), spec.key


def test_the_payments_settings_are_declared():
    assert exists("payments.over_limit_behaviour")
    assert exists("payments.overdue_behaviour")
    assert exists("payments.till_variance_tolerance")


# --------------------------------------------------------------------------- reading values
def test_a_string_from_a_form_is_read_as_the_right_type(clean_registry):
    """Values arrive from forms, JSON bodies and spreadsheets as text. "false" must not be true."""
    spec = a_setting(clean_registry, kind=SettingKind.BOOLEAN, default=True)
    assert coerce(spec, "false") is False
    assert coerce(spec, "no") is False
    assert coerce(spec, "0") is False
    assert coerce(spec, "true") is True
    assert coerce(spec, "on") is True


def test_something_that_is_neither_yes_nor_no_is_refused(clean_registry):
    spec = a_setting(clean_registry, kind=SettingKind.BOOLEAN, default=True)
    with pytest.raises(SettingValueError, match="neither"):
        coerce(spec, "maybe")


def test_a_number_out_of_range_is_refused(clean_registry):
    spec = a_setting(clean_registry, kind=SettingKind.INTEGER, default=5, minimum=0, maximum=90)
    assert coerce(spec, "90") == 90
    with pytest.raises(SettingValueError, match="cannot be above"):
        coerce(spec, 91)
    with pytest.raises(SettingValueError, match="cannot be below"):
        coerce(spec, -1)


def test_a_decimal_keeps_its_precision(clean_registry):
    spec = a_setting(clean_registry, kind=SettingKind.DECIMAL, default=Decimal("1.00"))
    assert coerce(spec, "2.50") == Decimal("2.50")


def test_a_choice_outside_its_options_is_refused(clean_registry):
    spec = a_setting(
        clean_registry, kind=SettingKind.CHOICE, default="block", choices=("block", "warn")
    )
    assert coerce(spec, "warn") == "warn"
    with pytest.raises(SettingValueError, match="must be one of"):
        coerce(spec, "ignore")


def test_a_boolean_writes_back_as_words_not_python(clean_registry):
    spec = a_setting(clean_registry, kind=SettingKind.BOOLEAN, default=False)
    assert serialise(spec, True) == "true"
    assert serialise(spec, "yes") == "true"


# --------------------------------------------------------------------------- scopes
def test_a_setting_says_where_it_may_be_set(clean_registry):
    """A rounding rule belongs to the business, not to whoever is on the till."""
    spec = a_setting(clean_registry, scopes=(Scope.PLATFORM, Scope.TENANT))
    assert spec.allows(Scope.TENANT)
    assert not spec.allows(Scope.USER)


def test_a_setting_settable_nowhere_is_refused(clean_registry):
    with pytest.raises(ValueError, match="settable somewhere"):
        a_setting(clean_registry, scopes=())
