import uuid

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from pgvector.django import HnswIndex, VectorField


class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        INDEXED = "indexed"
        FAILED = "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300)
    source_path = models.CharField(max_length=500)
    doc_type = models.CharField(max_length=64)
    classification = models.CharField(
        max_length=64, blank=True
    )  # a pack label; blank = unsearchable
    version = models.CharField(max_length=32, blank=True)
    effective_date = models.DateField(null=True, blank=True)
    checksum = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    text = models.TextField(blank=True)  # full text, for summarising a whole document
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.title


class Chunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    order = models.PositiveIntegerField()
    section = models.CharField(max_length=300, blank=True)
    text = models.TextField()
    embedding = VectorField(dimensions=settings.JUTANT_EMBED_DIM, null=True)
    search_vector = SearchVectorField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document", "order"]
        constraints = [
            models.UniqueConstraint(fields=["document", "order"], name="chunk_document_order")
        ]
        indexes = [
            HnswIndex(
                name="chunk_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
            GinIndex(fields=["search_vector"], name="chunk_search_gin"),
        ]
