"""What a trace may contain.

Tool arguments are always recorded, masked, as the audit log records them. Prompts, model
replies, questions, answers and tool results are recorded only when content tracing is on
(JUTANT_TRACE_CONTENT), and masked too: email addresses, phone numbers, and account, card and
ID numbers down to their last four digits. Names and amounts are not masked, which is why
content tracing is off unless someone turns it on to investigate.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from core.privacy.masking import mask


@dataclass(frozen=True)
class TraceContent:
    include: bool = False
    patterns: Mapping[str, str] | None = field(default=None)  # None: the default patterns

    def text(self, value: Any) -> Any:
        return self.masked(value) if self.include else None

    def masked(self, value: Any) -> Any:
        return mask(value, self.patterns)
