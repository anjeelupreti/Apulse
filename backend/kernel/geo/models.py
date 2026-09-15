"""Administrative divisions of Nepal (7 provinces, 77 districts, 753 local levels)."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from kernel.foundation.models import BaseModel


class Province(BaseModel):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100, unique=True)
    name_ne = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.name


class District(BaseModel):
    province = models.ForeignKey(Province, on_delete=models.PROTECT, related_name="districts")
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    name_ne = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["province", "name"], name="geo_unique_district_name")
        ]

    def __str__(self) -> str:
        return self.name


class LocalLevelType(models.TextChoices):
    METROPOLITAN = "metropolitan", _("Metropolitan City")
    SUB_METROPOLITAN = "sub_metropolitan", _("Sub-Metropolitan City")
    MUNICIPALITY = "municipality", _("Municipality")
    RURAL_MUNICIPALITY = "rural_municipality", _("Rural Municipality")


class LocalLevel(BaseModel):
    district = models.ForeignKey(District, on_delete=models.PROTECT, related_name="local_levels")
    code = models.CharField(max_length=15, unique=True)
    name = models.CharField(max_length=120)
    name_ne = models.CharField(max_length=120, blank=True)
    type = models.CharField(max_length=20, choices=LocalLevelType.choices)
    ward_count = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["district", "name"], name="geo_unique_local_level_name")
        ]

    def __str__(self) -> str:
        return self.name
