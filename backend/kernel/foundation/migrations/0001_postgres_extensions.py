from django.contrib.postgres.operations import (
    CryptoExtension,
    TrigramExtension,
    UnaccentExtension,
)
from django.db import migrations


class Migration(migrations.Migration):
    """PostgreSQL extensions required platform-wide (all are trusted extensions: no superuser)."""

    initial = True
    dependencies = []

    operations = [
        CryptoExtension(),
        TrigramExtension(),
        UnaccentExtension(),
    ]
