"""The "current tenant" for the running request, task or script.

Two things must agree: the Python-side context variable (used by model managers) and the
PostgreSQL session setting ``app.tenant_id`` (used by row-level security policies).
``tenant_context()`` sets both; nothing else should set either.
"""

from collections.abc import Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from uuid import UUID

from django.db import DEFAULT_DB_ALIAS, connections, transaction

PG_SETTING = "app.tenant_id"

_current_tenant_id: ContextVar[UUID | None] = ContextVar("current_tenant_id", default=None)


def get_current_tenant_id() -> UUID | None:
    """The tenant this code is running for, or None outside any tenant context."""
    return _current_tenant_id.get()


def require_current_tenant_id() -> UUID:
    tenant_id = _current_tenant_id.get()
    if tenant_id is None:
        raise NoActiveTenantError(
            "No active tenant. Wrap this code in `with tenant_context(tenant_id): ...`."
        )
    return tenant_id


class NoActiveTenantError(RuntimeError):
    """Raised when tenant-scoped data is touched with no tenant context set."""


def _read_db_tenant(using: str) -> str:
    with connections[using].cursor() as cursor:
        cursor.execute(f"SELECT current_setting('{PG_SETTING}', true)")
        row = cursor.fetchone()
    return (row[0] if row else "") or ""


def _write_db_tenant(value: str, using: str) -> None:
    # SET LOCAL (not SET) so the value dies with the transaction. A session-level SET would
    # leak across tenants as soon as PgBouncer hands the connection to the next request.
    with connections[using].cursor() as cursor:
        cursor.execute(f"SET LOCAL {PG_SETTING} = %s", [value])


@contextmanager
def tenant_context(tenant_id: UUID | str, *, using: str = DEFAULT_DB_ALIAS) -> Iterator[UUID]:
    """Run a block as one tenant.

    Opens a transaction, because ``SET LOCAL`` only has meaning inside one. When called inside an
    existing transaction this nests as a savepoint and the setting applies to the outer
    transaction, so the previous value is restored on exit.
    """
    tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
    token = _current_tenant_id.set(tenant_uuid)
    try:
        with transaction.atomic(using=using):
            previous = _read_db_tenant(using)
            _write_db_tenant(str(tenant_uuid), using)
            try:
                yield tenant_uuid
            finally:
                # Best effort: if the block failed, the transaction may already be aborted and
                # any statement would raise, masking the real exception.
                if not transaction.get_connection(using).needs_rollback:
                    with suppress(Exception):  # never mask the original error
                        _write_db_tenant(previous, using)
    finally:
        _current_tenant_id.reset(token)
