from django.contrib import admin

from apps.actions.models import ProposedAction


@admin.register(ProposedAction)
class ProposedActionAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "reference", "staff_id", "created_at", "decided_at")
    list_filter = ("status", "action_id")
    search_fields = ("reference", "staff_id")
    readonly_fields = [f.name for f in ProposedAction._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False
