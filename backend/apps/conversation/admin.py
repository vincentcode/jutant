from django.contrib import admin

from apps.conversation import selectors
from apps.conversation.models import Conversation, Feedback, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("role", "content", "feature_id", "citations", "created_at")
    can_delete = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "staff_id", "title", "updated_at")
    inlines = [MessageInline]


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    """Staff ratings of answers. Filter on thumbs-down to find answers to fix and questions to
    add to the evals (`manage.py export_feedback` writes them as drafts)."""

    list_display = ("updated_at", "rating", "reason", "feature", "question", "answer", "comment")
    list_filter = ("rating", "reason", "message__feature_id")
    search_fields = ("comment", "message__content", "staff_id")
    list_select_related = ("message",)
    readonly_fields = ("staff_id", "role", "rating", "reason", "comment", "question", "answer")
    fields = readonly_fields

    @admin.display(description="feature")
    def feature(self, obj: Feedback) -> str:
        return obj.message.feature_id

    @admin.display(description="question")
    def question(self, obj: Feedback) -> str:
        asked = selectors.question_before(obj.message)
        return asked.content if asked else ""

    @admin.display(description="answer")
    def answer(self, obj: Feedback) -> str:
        text = obj.message.content
        return text if len(text) <= 300 else f"{text[:300]}…"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
