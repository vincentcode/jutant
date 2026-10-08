"""The platform's feature templates."""

from core.features.templates.base import FeatureContext, FeatureTemplate
from core.features.templates.checklist import ChecklistTemplate
from core.features.templates.conversation import ConversationTemplate
from core.features.templates.document_extraction import DocumentExtractionTemplate
from core.features.templates.document_qa import DocumentQaTemplate
from core.features.templates.guided_playbook import GuidedPlaybookTemplate
from core.features.templates.record_lookup import RecordLookupTemplate
from core.features.templates.record_summary import RecordSummaryTemplate

TEMPLATES: dict[str, FeatureTemplate] = {
    t.id: t
    for t in (
        DocumentQaTemplate(),
        RecordLookupTemplate(),
        RecordSummaryTemplate(),
        GuidedPlaybookTemplate(),
        DocumentExtractionTemplate(),
        ChecklistTemplate(),
        ConversationTemplate(),
    )
}

__all__ = ["TEMPLATES", "FeatureContext", "FeatureTemplate"]
