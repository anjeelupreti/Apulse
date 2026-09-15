"""Guards that keep the root healthy: no missing migrations, valid OpenAPI schema."""

from io import StringIO

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_no_model_changes_without_migrations():
    out = StringIO()
    call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)


def test_openapi_schema_generates_without_warnings(tmp_path):
    schema_file = tmp_path / "schema.yaml"
    call_command("spectacular", "--validate", "--fail-on-warn", "--file", str(schema_file))
    assert schema_file.read_text(encoding="utf-8").startswith("openapi: 3")


def test_custom_user_model_is_active():
    from django.contrib.auth import get_user_model

    assert get_user_model()._meta.label == "identity.User"
