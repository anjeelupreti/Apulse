"""Items, the packs they come in, and the barcodes on those packs."""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from kernel.foundation.models import ArchivableModel, BaseModel
from kernel.tenancy.models import TenantScopedModel

#: Quantities are held to three decimals in base units — enough for 2.5 ml without inviting
#: fractions of a tablet by accident.
QUANTITY_DECIMALS = 3
#: Pack factors allow six, so an odd pack like 1 bottle = 66.667 ml still converts cleanly.
FACTOR_DECIMALS = 6


class UnitOfMeasure(BaseModel):
    """Tablet, strip, box, millilitre. Shared by every account: a tablet is a tablet."""

    code = models.SlugField(max_length=20, unique=True)
    name = models.CharField(max_length=50)
    #: Stored rather than derived: English pluralisation is not a rule ("boxes", not "boxs").
    #: Nepali needs no equivalent, because a noun after a numeral does not take a plural marker.
    name_plural = models.CharField(max_length=50, blank=True)
    name_ne = models.CharField(max_length=50, blank=True)
    #: Whether half of one means anything. Half a millilitre does; half a tablet is a decision a
    #: pharmacy makes deliberately, so it defaults to false.
    allows_fractions = models.BooleanField(default=False)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.name

    def label_for(self, quantity: Decimal | int) -> str:
        if Decimal(str(quantity)) == 1:
            return self.name.lower()
        return (self.name_plural or f"{self.name}s").lower()


class ItemType(models.TextChoices):
    MEDICINE = "medicine", _("Medicine")
    DEVICE = "device", _("Medical device")
    CONSUMABLE = "consumable", _("Consumable")
    COSMETIC = "cosmetic", _("Cosmetic")
    GENERAL = "general", _("General goods")
    SERVICE = "service", _("Service")


class ItemCategory(TenantScopedModel, ArchivableModel):
    """A pharmacy's own grouping of stock, nested as deeply as it likes."""

    parent = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="children"
    )
    code = models.SlugField(max_length=50)
    name = models.CharField(max_length=100)
    name_ne = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name_plural = "item categories"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="catalog_unique_category_code")
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def path(self) -> str:
        names = [self.name]
        parent = self.parent
        while parent is not None:
            names.append(parent.name)
            parent = parent.parent
        return " / ".join(reversed(names))


class Manufacturer(TenantScopedModel, ArchivableModel):
    name = models.CharField(max_length=150)
    name_ne = models.CharField(max_length=150, blank=True)
    country = models.CharField(max_length=60, blank=True)
    #: Importers and distributors need the licence on file for DDA inspection.
    licence_number = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"], name="catalog_unique_manufacturer_name"
            )
        ]

    def __str__(self) -> str:
        return self.name


class Item(TenantScopedModel, ArchivableModel):
    """Something a pharmacy stocks.

    Medicines add their own details (generic name, strength, drug schedule) in the pharmacy
    module; what lives here is true of a bandage and a bottle of shampoo as well.
    """

    code = models.SlugField(max_length=50, help_text=_("Internal code or SKU."))
    name = models.CharField(max_length=200)
    name_ne = models.CharField(max_length=200, blank=True)
    item_type = models.CharField(max_length=20, choices=ItemType.choices, default=ItemType.MEDICINE)
    category = models.ForeignKey(
        ItemCategory, on_delete=models.PROTECT, null=True, blank=True, related_name="items"
    )
    manufacturer = models.ForeignKey(
        Manufacturer, on_delete=models.PROTECT, null=True, blank=True, related_name="items"
    )

    base_unit = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name="+",
        help_text=_("The smallest unit stock is counted in. Everything converts to this."),
    )
    #: Required, and deliberately without a default: whether a medicine carries VAT is a decision
    #: about the VAT Act, not something this code should assume (CR-IRD-01).
    tax_category = models.ForeignKey("tax.TaxCategory", on_delete=models.PROTECT, related_name="+")

    is_batch_tracked = models.BooleanField(
        default=True, help_text=_("Stock is held per batch. Required for anything with an expiry.")
    )
    is_expiry_tracked = models.BooleanField(default=True)
    allow_loose_sale = models.BooleanField(
        default=True,
        help_text=_("Single base units may be sold, such as four tablets out of a strip."),
    )

    #: Default printed price per base unit, used when stock carries none of its own.
    #: Medicines normally price per batch, because the printed price differs between lots;
    #: general goods such as a thermometer have one price that belongs to the item.
    mrp = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, verbose_name=_("MRP")
    )

    hs_code = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="catalog_unique_item_code"),
            models.CheckConstraint(
                # An expiry date belongs to a batch, so expiry tracking without batch tracking
                # would have nowhere to put it.
                condition=models.Q(is_expiry_tracked=False) | models.Q(is_batch_tracked=True),
                name="catalog_expiry_requires_batches",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "name"])]

    def __str__(self) -> str:
        return self.name


class ItemUnit(TenantScopedModel):
    """A pack this item is bought or sold in, and how many base units it holds.

    A strip of ten tablets is `factor=10`; a box of ten strips is `factor=100`. Factors are always
    against the base unit rather than the pack below, so a wrong middle row cannot quietly scale
    everything above it.
    """

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="units")
    unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name="+")
    factor = models.DecimalField(
        max_digits=18,
        decimal_places=FACTOR_DECIMALS,
        validators=[MinValueValidator(Decimal("0.000001"))],
        help_text=_("Base units in one of these."),
    )
    is_purchase_default = models.BooleanField(default=False)
    is_sale_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["item", "factor"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "item", "unit"], name="catalog_unique_item_unit"
            ),
            models.CheckConstraint(
                condition=models.Q(factor__gt=0), name="catalog_factor_positive"
            ),
            models.UniqueConstraint(
                fields=["tenant", "item"],
                condition=models.Q(is_purchase_default=True),
                name="catalog_one_purchase_default",
            ),
            models.UniqueConstraint(
                fields=["tenant", "item"],
                condition=models.Q(is_sale_default=True),
                name="catalog_one_sale_default",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.unit.code} = {self.factor} {self.item.base_unit.code}"

    @property
    def is_base(self) -> bool:
        return self.factor == 1


class ItemBarcode(TenantScopedModel):
    """A barcode, which identifies a pack rather than an item.

    A box and a strip of the same medicine scan differently, and scanning the box must add a box.
    """

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="barcodes")
    item_unit = models.ForeignKey(
        ItemUnit,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="barcodes",
        help_text=_("Which pack this barcode is printed on. Blank means the base unit."),
    )
    code = models.CharField(max_length=64)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["item", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="catalog_unique_barcode_per_tenant",
            )
        ]
        indexes = [models.Index(fields=["tenant", "code"])]

    def __str__(self) -> str:
        return self.code
