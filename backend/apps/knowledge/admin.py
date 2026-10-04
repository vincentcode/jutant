"""Tagging screen for operations staff."""

from django.contrib import admin

from apps.knowledge.models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "doc_type", "classification", "status", "effective_date")
    list_filter = ("doc_type", "classification", "status")
    search_fields = ("title", "source_path")
    readonly_fields = ("checksum", "status", "created_at")
