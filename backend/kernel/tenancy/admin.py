from django.contrib import admin

from .models import Tenant, TenantDomain, TenantMembership

# Only registry models are registered. Tenant-scoped models (LegalEntity, Branch, Location) use a
# tenant-filtered default manager and row-level security, so they would show nothing in the
# cross-tenant Django admin; they are administered through the product UI and the control plane.


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin[Tenant]):
    list_display = ("slug", "name", "status", "tier", "created_at")
    list_filter = ("status", "tier")
    search_fields = ("slug", "name", "name_ne")
    readonly_fields = ("id", "created_at", "updated_at", "status_changed_at")


@admin.register(TenantDomain)
class TenantDomainAdmin(admin.ModelAdmin[TenantDomain]):
    list_display = ("domain", "tenant", "is_primary", "is_verified")
    list_filter = ("is_primary", "is_verified")
    search_fields = ("domain",)


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin[TenantMembership]):
    list_display = ("user", "tenant", "status")
    list_filter = ("status",)
    search_fields = ("user__email", "user__phone", "tenant__slug")
