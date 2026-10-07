import uuid

from django.db import models


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff_id = models.CharField(max_length=64, db_index=True)  # the caller's staff number
    title = models.CharField(max_length=200, blank=True)
    # What staff are talking about: the stack of subjects (core.context), kept between turns.
    context = models.JSONField(default=dict, blank=True)
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
    steps = models.JSONField(default=list, blank=True)  # playbook steps the turn showed
    trace = models.JSONField(default=dict, blank=True)  # the answer's trace, for feedback
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


class Feedback(models.Model):
    """A staff member's rating of an answer: one per person per answer, which they can change.
    Thumbs-down answers are candidates for new eval questions."""

    class Rating(models.TextChoices):
        UP = "up"
        DOWN = "down"

    class Reason(models.TextChoices):
        WRONG_ANSWER = "wrong_answer", "Wrong answer"
        WRONG_SOURCE = "wrong_source", "Wrong source"
        WRONG_FEATURE = "wrong_feature", "Wrong kind of help"
        TOO_SLOW = "too_slow", "Too slow"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="feedback")
    staff_id = models.CharField(max_length=64)
    role = models.CharField(max_length=64)  # the rater's role then, to replay the question as
    rating = models.CharField(max_length=8, choices=Rating.choices)
    reason = models.CharField(max_length=32, choices=Reason.choices, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["message", "staff_id"], name="feedback_once_per_staff")
        ]
        indexes = [models.Index(fields=["rating", "updated_at"])]
