from django.apps import AppConfig


class AuditConfig(AppConfig):
    name = "kernel.audit"
    label = "audit"
    verbose_name = "Audit trail"
