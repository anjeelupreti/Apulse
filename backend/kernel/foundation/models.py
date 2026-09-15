"""Abstract base models. Every domain model builds on these (docs/ARCHITECTURE.md §6)."""

from django.db import models
from django.utils import timezone

from shared.ids import uuid7


class UUIDModel(models.Model):
    """UUIDv7 primary key: time-ordered and safe to generate on offline clients."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class ArchivableModel(models.Model):
    """Soft archive for master data. Transactional documents are never archived or deleted."""

    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    def archive(self) -> None:
        if self.archived_at is None:
            self.archived_at = timezone.now()
            self.save(update_fields=["archived_at", *self._touched_fields()])

    def restore(self) -> None:
        if self.archived_at is not None:
            self.archived_at = None
            self.save(update_fields=["archived_at", *self._touched_fields()])

    def _touched_fields(self) -> list[str]:
        return ["updated_at"] if any(f.name == "updated_at" for f in self._meta.fields) else []


class VersionedModel(models.Model):
    """Optimistic concurrency: clients send `version`; a stale value yields VERSION_CONFLICT."""

    version = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True
