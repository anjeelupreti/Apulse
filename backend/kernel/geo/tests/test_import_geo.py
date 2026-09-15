import pytest
from django.core.management import CommandError, call_command

from kernel.geo.models import District, LocalLevel, Province

pytestmark = pytest.mark.django_db


def test_bundled_provinces_import():
    call_command("import_geo", verbosity=0)
    assert Province.objects.count() == 7
    assert Province.objects.filter(name="Bagmati").exists()
    assert Province.objects.get(code="P3").name_ne == "बागमती"


def test_import_is_idempotent():
    call_command("import_geo", verbosity=0)
    call_command("import_geo", verbosity=0)
    assert Province.objects.count() == 7


def test_districts_import_from_a_supplied_file(tmp_path):
    call_command("import_geo", verbosity=0)
    csv_file = tmp_path / "districts.csv"
    csv_file.write_text(
        "code,province_code,name,name_ne\nD27,P3,Kathmandu,काठमाडौँ\n", encoding="utf-8"
    )
    call_command("import_geo", districts=csv_file, verbosity=0)
    district = District.objects.get(code="D27")
    assert district.name == "Kathmandu"
    assert district.province.code == "P3"


def test_unknown_province_code_is_rejected(tmp_path):
    call_command("import_geo", verbosity=0)
    csv_file = tmp_path / "districts.csv"
    csv_file.write_text("code,province_code,name,name_ne\nD99,P9,Nowhere,\n", encoding="utf-8")
    with pytest.raises(CommandError, match="Unknown province code"):
        call_command("import_geo", districts=csv_file, verbosity=0)


def test_unknown_local_level_type_is_rejected(tmp_path):
    call_command("import_geo", verbosity=0)
    districts = tmp_path / "districts.csv"
    districts.write_text("code,province_code,name,name_ne\nD27,P3,Kathmandu,\n", encoding="utf-8")
    call_command("import_geo", districts=districts, verbosity=0)

    local_levels = tmp_path / "local_levels.csv"
    local_levels.write_text(
        "code,district_code,name,name_ne,type,ward_count\nL1,D27,Kathmandu,,city,32\n",
        encoding="utf-8",
    )
    with pytest.raises(CommandError, match="Unknown local level type"):
        call_command("import_geo", local_levels=local_levels, verbosity=0)
    assert LocalLevel.objects.count() == 0


def test_missing_file_is_reported_clearly(tmp_path):
    with pytest.raises(CommandError, match="File not found"):
        call_command("import_geo", provinces=tmp_path / "nope.csv", verbosity=0)
