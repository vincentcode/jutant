from django.contrib import admin

from apps.identity.models import LoginAttempt, Staff


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ("staff_number", "role", "is_active", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("staff_number", "user__username")


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    """Read-only. Deleting a username's recent failures lifts its sign-in lock early."""

    list_display = ("created_at", "username", "ip", "succeeded")
    list_filter = ("succeeded",)
    search_fields = ("username", "ip")

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
