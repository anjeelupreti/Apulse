from django.contrib import admin

from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin[User]):
    list_display = ("full_name", "email", "phone", "is_active", "is_staff", "created_at")
    search_fields = ("full_name", "email", "phone")
    list_filter = ("is_active", "is_staff", "preferred_language")
    readonly_fields = ("id", "created_at", "updated_at", "last_login", "password")
    exclude = ("groups", "user_permissions")
