"""Audit records and the per-tenant hash chain that protects them."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from kernel.tenancy.models import TenantScopedModel

#: First link of every tenant's chain.
GENESIS_HASH = "0" * 64


class AuditAction(models.TextChoices):
    CREATE = "create", _("Created")
    UPDATE = "update", _("Changed")
    ARCHIVE = "archive", _("Archived")
    RESTORE = "restore", _("Restored")
    DELETE = "delete", _("Deleted")
    LOGIN = "login", _("Signed in")
    LOGOUT = "logout", _("Signed out")
    EXPORT = "export", _("Exported")
    PRINT = "print", _("Printed")
    REPRINT = "reprint", _("Reprinted")
    VIEW_SENSITIVE = "view_sensitive", _("Viewed sensitive data")
    OVERRIDE = "override", _("Overrode a rule")
    VOID = "void", _("Voided")
    PERMISSION_CHANGE = "permission_change", _("Changed access")
    SETTINGS_CHANGE = "settings_change", _("Changed settings")
    IMPERSONATION_START = "impersonation_start", _("Support access started")
    IMPERSONATION_END = "impersonation_end", _("Support access ended")


class AuditEvent(TenantScopedModel):
    """One recorded action. Rows are inserted and never changed — see migration 0002."""

    #: Position in this tenant's chain, starting at 1.
    sequence = models.BigIntegerField()
    previous_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64)

    action = models.CharField(max_length=30, choices=AuditAction.choices, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    #: Kept as text as well, so the record still reads correctly years later.
    actor_label = models.CharField(max_length=200, blank=True)

    entity_type = models.CharField(max_length=100, blank=True, help_text="app_label.ModelName")
    entity_id = models.CharField(max_length=64, blank=True)
    entity_label = models.CharField(max_length=300, blank=True)
    branch = models.ForeignKey(
        "tenancy.Branch", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    #: {field: {"from": ..., "to": ...}} with secret-looking fields masked.
    changes = models.JSONField(default=dict, blank=True)
    #: request id, IP, user agent, device — whatever identified the caller.
    context = models.JSONField(default=dict, blank=True)
    #: Why, for actions that require a justification (overrides, voids, corrections).
    reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "sequence"], name="audit_unique_sequence_per_tenant"
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "entity_type", "entity_id"]),
            models.Index(fields=["tenant", "actor", "-created_at"]),
            models.Index(fields=["tenant", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"#{self.sequence} {self.action} {self.entity_type}"


class AuditChainHead(TenantScopedModel):
    """The tip of a tenant's chain. Locked while appending, so entries cannot interleave."""

    sequence = models.BigIntegerField(default=0)
    last_hash = models.CharField(max_length=64, default=GENESIS_HASH)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="audit_one_chain_head_per_tenant")
        ]

    def __str__(self) -> str:
        return f"chain at #{self.sequence}"
