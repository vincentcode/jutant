"""The conversation's context: what staff are talking about, kept as a stack of frames.

A frame is one subject: the entities it is about (a transfer, a product), the feature serving
it, and, for a procedure, the run it holds. A new subject pushes a frame; returning to an
earlier one brings it back to the top; nothing is lost by a detour. Each turn is read against
the stack (`reader`), and lookups take their arguments from the active frame.

Entity types come from the pack, so `core/` names none: it knows "an entity of some type".
"""

from core.context.entities import DOCUMENT, entities_in, from_calls, names_in, values_in
from core.context.stack import ContextStack, Frame

__all__ = [
    "DOCUMENT",
    "ContextStack",
    "Frame",
    "entities_in",
    "from_calls",
    "names_in",
    "values_in",
]
