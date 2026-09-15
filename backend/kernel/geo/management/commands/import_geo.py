"""Load Nepal's administrative divisions from CSV.

    python tasks.py -- manage import_geo                      # bundled provinces
    manage.py import_geo --districts path/to/districts.csv
    manage.py import_geo --local-levels path/to/local_levels.csv

Provinces are bundled. Districts and local levels are **not**: they must come from an official
source (see COMPLIANCE_REGISTER CR-GEO-01) rather than from memory, because branch addresses and
DDA correspondence depend on the exact spellings.

CSV columns
    provinces.csv      code,name,name_ne
    districts.csv      code,province_code,name,name_ne
    local_levels.csv   code,district_code,name,name_ne,type,ward_count
"""

import csv
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from kernel.geo.models import District, LocalLevel, LocalLevelType, Province

BUNDLED_PROVINCES = Path(__file__).resolve().parents[2] / "data" / "provinces.csv"


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise CommandError(f"File not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]


class Command(BaseCommand):
    help = "Import provinces, districts and local levels from CSV (idempotent)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--provinces", type=Path, default=BUNDLED_PROVINCES)
        parser.add_argument("--districts", type=Path)
        parser.add_argument("--local-levels", type=Path)

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ARG002 (Django signature)
        created, updated = self._import_provinces(options["provinces"])
        self.stdout.write(f"provinces: {created} created, {updated} updated")

        if options["districts"]:
            created, updated = self._import_districts(options["districts"])
            self.stdout.write(f"districts: {created} created, {updated} updated")
        elif not District.objects.exists():
            self.stdout.write(
                self.style.WARNING(
                    "No districts loaded. Supply an official list with --districts "
                    "(see COMPLIANCE_REGISTER CR-GEO-01)."
                )
            )

        if options["local_levels"]:
            created, updated = self._import_local_levels(options["local_levels"])
            self.stdout.write(f"local levels: {created} created, {updated} updated")

    def _import_provinces(self, path: Path) -> tuple[int, int]:
        created = updated = 0
        for row in _rows(path):
            _, was_created = Province.objects.update_or_create(
                code=row["code"], defaults={"name": row["name"], "name_ne": row.get("name_ne", "")}
            )
            created, updated = (created + 1, updated) if was_created else (created, updated + 1)
        return created, updated

    def _import_districts(self, path: Path) -> tuple[int, int]:
        provinces = {province.code: province for province in Province.objects.all()}
        created = updated = 0
        for row in _rows(path):
            province = provinces.get(row["province_code"])
            if province is None:
                raise CommandError(
                    f"Unknown province code {row['province_code']!r} for {row['name']!r}"
                )
            _, was_created = District.objects.update_or_create(
                code=row["code"],
                defaults={
                    "province": province,
                    "name": row["name"],
                    "name_ne": row.get("name_ne", ""),
                },
            )
            created, updated = (created + 1, updated) if was_created else (created, updated + 1)
        return created, updated

    def _import_local_levels(self, path: Path) -> tuple[int, int]:
        districts = {district.code: district for district in District.objects.all()}
        valid_types = set(LocalLevelType.values)
        created = updated = 0
        for row in _rows(path):
            district = districts.get(row["district_code"])
            if district is None:
                raise CommandError(
                    f"Unknown district code {row['district_code']!r} for {row['name']!r}"
                )
            if row["type"] not in valid_types:
                raise CommandError(f"Unknown local level type {row['type']!r} for {row['name']!r}")
            ward_count = row.get("ward_count") or ""
            _, was_created = LocalLevel.objects.update_or_create(
                code=row["code"],
                defaults={
                    "district": district,
                    "name": row["name"],
                    "name_ne": row.get("name_ne", ""),
                    "type": row["type"],
                    "ward_count": int(ward_count) if ward_count.isdigit() else None,
                },
            )
            created, updated = (created + 1, updated) if was_created else (created, updated + 1)
        return created, updated
