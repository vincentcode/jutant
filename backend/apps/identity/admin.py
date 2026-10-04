from django.contrib import admin

from apps.identity.models import Staff


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ("staff_number", "role", "is_active", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("staff_number", "user__username")
