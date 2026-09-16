from django.contrib import admin

from .models import LoginAttempt, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin[User]):
    list_display = ("full_name", "email", "phone", "is_active", "is_staff", "created_at")
    search_fields = ("full_name", "email", "phone")
    list_filter = ("is_active", "is_staff", "preferred_language")
    readonly_fields = ("id", "created_at", "updated_at", "last_login", "password")
    exclude = ("groups", "user_permissions")


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin[LoginAttempt]):
    """Read-only security log: entries are evidence and are never edited."""

    list_display = ("created_at", "identifier", "outcome", "tenant_slug", "ip_address")
    list_filter = ("outcome",)
    search_fields = ("identifier", "ip_address", "tenant_slug")
    readonly_fields = tuple(field.name for field in LoginAttempt._meta.fields)

    def has_add_permission(self, request: object) -> bool:  # noqa: ARG002 (Django signature)
        return False

    def has_change_permission(self, request: object, obj: object = None) -> bool:  # noqa: ARG002
        return False
