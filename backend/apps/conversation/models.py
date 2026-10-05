import uuid

from django.db import models


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff_id = models.CharField(max_length=64, db_index=True)  # the caller's staff number
    title = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.title or str(self.id)


class Message(models.Model):
    class Role(models.TextChoices):
        SYSTEM = "system"
        USER = "user"
        ASSISTANT = "assistant"
        TOOL = "tool"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    content = models.TextField(blank=True)
    feature_id = models.CharField(max_length=64, blank=True)
    tool_call_id = models.CharField(max_length=64, blank=True)
    tool_calls = models.JSONField(default=list, blank=True)
    citations = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["conversation", "created_at"])]


class Upload(models.Model):
    """A file staff uploaded into a conversation, for extraction. Its text is used in that
    conversation only and is never added to the search index."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="uploads")
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
