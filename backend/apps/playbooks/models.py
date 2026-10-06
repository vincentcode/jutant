import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models


class Playbook(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=100, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.title


class Step(models.Model):
    class Expects(models.TextChoices):
        CONFIRM = "confirm"
        CHOICE = "choice"
        TEXT = "text"
        NONE = "none"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    playbook = models.ForeignKey(Playbook, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    instruction = models.TextField()
    audience = ArrayField(models.CharField(max_length=32))
    expects = models.CharField(max_length=16, choices=Expects.choices, default=Expects.CONFIRM)
    choices = models.JSONField(default=list, blank=True)
    next_on = models.JSONField(default=dict, blank=True)
    # {tool, argument, pattern}: a record the step looks up with the reply
    lookup = models.JSONField(null=True, blank=True)
    answer_from = models.CharField(max_length=100, blank=True)  # e.g. "1.status"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["playbook", "order"]
        constraints = [
            models.UniqueConstraint(fields=["playbook", "order"], name="step_playbook_order")
        ]


class PlaybookRun(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        COMPLETED = "completed"
        ABANDONED = "abandoned"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation_id = models.UUIDField(db_index=True)  # cross-app reference: plain id
    playbook_id = models.CharField(max_length=100)  # playbook slug
    current_order = models.PositiveIntegerField()
    answers = models.JSONField(default=dict, blank=True)
    facts = models.JSONField(default=dict, blank=True)  # step order -> the record it looked up
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    feature_id = models.CharField(max_length=64, blank=True)  # the feature that started the run
    created_at = models.DateTimeField(auto_now_add=True)
