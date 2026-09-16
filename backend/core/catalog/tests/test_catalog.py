"""Packs and base units: the arithmetic a counter does all day without thinking about it."""

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from core.catalog.models import Item, ItemUnit, UnitOfMeasure
from core.catalog.services import (
    add_barcode,
    add_pack,
    create_item,
    describe_quantity,
    find_by_barcode,
    from_base,
    to_base,
    validate_quantity,
)
from kernel.tenancy.context import tenant_context
from shared.errors import DomainError

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _inside_tenant(provisioned):
    with tenant_context(provisioned.tenant.id):
        yield


# --------------------------------------------------------------------------- units
def test_the_common_units_are_seeded():
    codes = set(UnitOfMeasure.objects.values_list("code", flat=True))
    assert {"tab", "cap", "strip", "box", "ml", "bottle"} <= codes


def test_liquids_allow_fractions_and_tablets_do_not():
    """2.5 ml is a dose. Half a tablet is a decision a pharmacy makes deliberately."""
    assert UnitOfMeasure.objects.get(code="ml").allows_fractions
    assert not UnitOfMeasure.objects.get(code="tab").allows_fractions


# --------------------------------------------------------------------------- building
def test_an_item_gets_a_base_pack_automatically(units, exempt_category):
    item = create_item(
        code="BAND-01", name="Gauze bandage", base_unit=units["pcs"], tax_category=exempt_category
    )
    base = ItemUnit.objects.get(item=item, unit=units["pcs"])
    assert base.factor == 1
    assert base.is_sale_default


def test_creating_an_item_is_audited(units, exempt_category):
    from kernel.audit.models import AuditAction, AuditEvent

    create_item(
        code="BAND-01", name="Gauze bandage", base_unit=units["pcs"], tax_category=exempt_category
    )
    event = AuditEvent.objects.filter(action=AuditAction.CREATE).first()
    assert event is not None
    assert event.changes["name"]["to"] == "Gauze bandage"


def test_packs_are_measured_against_the_base_unit(paracetamol, units):
    """A box is 100 tablets, not 10 strips: a wrong middle row cannot scale everything above it."""
    assert ItemUnit.objects.get(item=paracetamol, unit=units["strip"]).factor == 10
    assert ItemUnit.objects.get(item=paracetamol, unit=units["box"]).factor == 100


def test_an_empty_pack_is_refused(paracetamol, units):
    with pytest.raises(ValueError, match="more than zero"):
        add_pack(paracetamol, units["carton"], Decimal("0"))


def test_only_one_pack_can_be_the_purchase_default(paracetamol, units):
    add_pack(paracetamol, units["carton"], Decimal("1000"), is_purchase_default=True)
    assert ItemUnit.objects.filter(item=paracetamol, is_purchase_default=True).count() == 1
    assert ItemUnit.objects.get(item=paracetamol, is_purchase_default=True).unit.code == "carton"


def test_an_item_code_is_unique_within_a_pharmacy(units, exempt_category):
    create_item(code="DUP", name="First", base_unit=units["pcs"], tax_category=exempt_category)
    with pytest.raises(IntegrityError), transaction.atomic():
        create_item(code="DUP", name="Second", base_unit=units["pcs"], tax_category=exempt_category)


def test_expiry_tracking_requires_batches(units, exempt_category):
    """An expiry date belongs to a batch, so there would be nowhere to record it."""
    with pytest.raises(IntegrityError), transaction.atomic():
        Item.objects.create(
            code="ODD",
            name="Odd",
            base_unit=units["pcs"],
            tax_category=exempt_category,
            is_batch_tracked=False,
            is_expiry_tracked=True,
        )


# --------------------------------------------------------------------------- conversion
def test_packs_convert_to_base_units(paracetamol, units):
    assert to_base(paracetamol, 3, units["box"]) == Decimal("300.000")
    assert to_base(paracetamol, 2, units["strip"]) == Decimal("20.000")
    assert to_base(paracetamol, 7, units["tab"]) == Decimal("7.000")


def test_base_units_convert_back_to_packs(paracetamol, units):
    assert from_base(paracetamol, 300, units["box"]) == Decimal("3.000")
    assert from_base(paracetamol, 15, units["strip"]) == Decimal("1.500")


def test_converting_through_a_pack_the_item_does_not_use_is_refused(paracetamol, units):
    with pytest.raises(DomainError) as caught:
        to_base(paracetamol, 1, units["bottle"])
    assert caught.value.error.code == "ITEM_UNIT_UNKNOWN"


def test_a_round_trip_through_a_pack_is_lossless(paracetamol, units):
    for quantity in (1, 3, 17, 250):
        base = to_base(paracetamol, quantity, units["strip"])
        assert from_base(paracetamol, base, units["strip"]) == Decimal(quantity)


# --------------------------------------------------------------------------- readability
def test_a_quantity_reads_the_way_a_storekeeper_counts_it(paracetamol):
    """247 tablets means nothing on a shelf. Two boxes, four strips and seven tablets does."""
    assert describe_quantity(paracetamol, 247) == "2 boxes 4 strips 7 tablets"


def test_exact_pack_quantities_do_not_mention_loose_units(paracetamol):
    assert describe_quantity(paracetamol, 200) == "2 boxes"
    assert describe_quantity(paracetamol, 30) == "3 strips"


def test_singular_reads_correctly(paracetamol):
    assert describe_quantity(paracetamol, 101) == "1 box 1 tablet"


def test_nothing_in_stock_reads_as_zero(paracetamol):
    assert describe_quantity(paracetamol, 0) == "0 tablets"


def test_negative_stock_is_shown_as_negative(paracetamol):
    assert describe_quantity(paracetamol, -5) == "-5 tablets"


def test_an_item_with_no_packs_reads_in_base_units(units, exempt_category):
    item = create_item(
        code="SYR-5", name="Syringe 5ml", base_unit=units["pcs"], tax_category=exempt_category
    )
    assert describe_quantity(item, 12) == "12 pieces"


# --------------------------------------------------------------------------- validation
def test_a_fraction_of_a_tablet_is_refused(paracetamol):
    with pytest.raises(DomainError) as caught:
        validate_quantity(paracetamol, Decimal("1.5"))
    assert caught.value.error.code == "QUANTITY_NOT_WHOLE"


def test_a_fraction_of_a_millilitre_is_allowed(units, exempt_category):
    syrup = create_item(
        code="SYR-100", name="Cough syrup", base_unit=units["ml"], tax_category=exempt_category
    )
    validate_quantity(syrup, Decimal("2.5"))


def test_zero_and_negative_quantities_are_refused(paracetamol):
    for quantity in (Decimal("0"), Decimal("-1")):
        with pytest.raises(DomainError):
            validate_quantity(paracetamol, quantity)


def test_an_item_sold_only_in_full_packs_refuses_a_loose_quantity(units, exempt_category):
    kit = create_item(
        code="KIT-01",
        name="First aid kit refill",
        base_unit=units["pcs"],
        tax_category=exempt_category,
        allow_loose_sale=False,
    )
    pack = add_pack(kit, units["box"], Decimal("12"), is_sale_default=True)
    assert pack.factor == 12

    validate_quantity(kit, Decimal("24"))
    with pytest.raises(DomainError) as caught:
        validate_quantity(kit, Decimal("13"))
    assert caught.value.error.code == "LOOSE_SALE_NOT_ALLOWED"


def test_loose_sale_is_allowed_by_default(paracetamol):
    """Nepali pharmacies routinely sell four tablets out of a strip."""
    validate_quantity(paracetamol, Decimal("4"))


# --------------------------------------------------------------------------- barcodes
def test_scanning_a_box_adds_a_box(paracetamol, units):
    """Not one tablet. The barcode identifies the pack, not just the item."""
    box = ItemUnit.objects.get(item=paracetamol, unit=units["box"])
    add_barcode(paracetamol, "8901234567890", item_unit=box)

    item, pack = find_by_barcode("8901234567890")
    assert item == paracetamol
    assert pack.unit.code == "box"
    assert to_base(item, 1, pack.unit) == Decimal("100.000")


def test_a_barcode_with_no_pack_means_the_base_unit(paracetamol):
    add_barcode(paracetamol, "1111111111111")
    _item, pack = find_by_barcode("1111111111111")
    assert pack.factor == 1


def test_surrounding_space_from_a_scanner_is_ignored(paracetamol):
    add_barcode(paracetamol, "2222222222222")
    assert find_by_barcode("  2222222222222 ")[0] == paracetamol


def test_an_unknown_barcode_says_so(paracetamol):
    with pytest.raises(DomainError) as caught:
        find_by_barcode("0000000000000")
    assert caught.value.error.code == "ITEM_BARCODE_UNKNOWN"
    assert caught.value.error.message_ne


def test_a_barcode_cannot_point_at_two_items(paracetamol, units, exempt_category):
    add_barcode(paracetamol, "3333333333333")
    other = create_item(
        code="OTHER", name="Other", base_unit=units["pcs"], tax_category=exempt_category
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        add_barcode(other, "3333333333333")


# --------------------------------------------------------------------------- isolation
def test_catalogues_do_not_leak_between_pharmacies(units, exempt_category):
    create_item(code="MINE", name="My item", base_unit=units["pcs"], tax_category=exempt_category)
    other = make_tenant_for_isolation()
    with tenant_context(other.tenant.id):
        assert Item.objects.count() == 0
        # The same code and the same barcode are free for another pharmacy to use.
        create_item(
            code="MINE", name="Their item", base_unit=units["pcs"], tax_category=exempt_category
        )


def make_tenant_for_isolation():
    from kernel.tenancy.tests.factories import make_tenant

    return make_tenant("bravo")
