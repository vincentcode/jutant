from django.contrib import admin

from apps.identity.models import LoginAttempt, PackRole, Staff


class PackRoleInline(admin.TabularInline):
    """Roles in other packs: the same person as an employee in HR, say."""

    model = PackRole
    extra = 1
    fields = ("pack", "role", "attributes")


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ("staff_number", "role", "other_packs", "is_active", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("staff_number", "user__username")
    inlines = [PackRoleInline]

    @admin.display(description="Roles in other packs")
    def other_packs(self, staff: Staff) -> str:
        return ", ".join(str(r) for r in staff.pack_roles.all())


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
