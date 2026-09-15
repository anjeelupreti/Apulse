"""Managers that keep tenant-scoped queries scoped."""

from typing import Any, Self

from django.db import models

from .context import get_current_tenant_id


class TenantQuerySet(models.QuerySet[Any]):
    def for_tenant(self, tenant_id: Any) -> Self:
        return self.filter(tenant_id=tenant_id)


class TenantManager(models.Manager[Any]):
    """Default manager: every query is filtered to the current tenant.

    With no tenant context this returns nothing rather than everything — the same direction
    the database policies fail in, so a missing context surfaces as "no data" and never as
    another pharmacy's data.
    """

    def get_queryset(self) -> models.QuerySet[Any]:
        queryset = TenantQuerySet(self.model, using=self._db)
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            return queryset.none()
        return queryset.filter(tenant_id=tenant_id)


class AllTenantsManager(models.Manager[Any]):
    """Explicit escape hatch for provisioning and platform tooling.

    Row-level security still applies, so this widens the application filter only — it cannot be
    used to read across tenants on a normal connection.
    """

    def get_queryset(self) -> models.QuerySet[Any]:
        return TenantQuerySet(self.model, using=self._db)
