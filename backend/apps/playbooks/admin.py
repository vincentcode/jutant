"""Editing screen for operations staff."""

from django.contrib import admin

from apps.playbooks.models import Playbook, PlaybookRun, Step


class StepInline(admin.StackedInline):
    model = Step
    extra = 0


@admin.register(Playbook)
class PlaybookAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "is_active", "version")
    inlines = [StepInline]


@admin.register(PlaybookRun)
class PlaybookRunAdmin(admin.ModelAdmin):
    list_display = ("conversation_id", "playbook_id", "current_order", "status", "created_at")
    list_filter = ("status",)
