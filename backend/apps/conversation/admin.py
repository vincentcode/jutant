from django.contrib import admin

from apps.conversation.models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("role", "content", "feature_id", "citations", "created_at")
    can_delete = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "staff_id", "title", "updated_at")
    inlines = [MessageInline]
