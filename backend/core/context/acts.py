"""Dialogue acts: what a message does to the conversation's subjects.

Understanding a message is two decisions and some memory. The act says how the message relates
to the conversation; for a new subject, the router says which kind of help (the intent); the
context stack (`core.context.stack`) is the memory the act is applied to. The acts are the
platform's, the same in every pack:

- `new`: a new subject (the router finds its feature);
- `follow_up`: more about the subject on top;
- `return`: back to an earlier subject;
- `resume`: back to the procedure set aside for something else;
- `answer`: a reply to the step the procedure on top waits on;
- `stop`: end the procedure.

Every turn's reading is named as one of these and recorded with the state it was read in, so
the audit log holds labelled examples for training an act classifier. When one is set
(`DialogueActClassifier`), a confident act decides the reading where the act alone says which
subject; otherwise the code rules and the model's questions decide, as before.
"""

from dataclasses import dataclass
from typing import Literal

from core.context.reader import Reading
from core.context.stack import ContextStack

Act = Literal["new", "follow_up", "return", "resume", "answer", "stop"]
ACTS: tuple[Act, ...] = ("new", "follow_up", "return", "resume", "answer", "stop")


@dataclass(frozen=True)
class ActState:
    """What an act classifier knows of the conversation besides the message: whether a subject
    is open and what it is about, and whether a procedure is open and where."""

    subject: str | None = None  # what the subject on top is about ("transfer TX-0002")
    procedure: str | None = None  # the open procedure's title ("Failed transfer")
    procedure_on_top: bool = False  # it waits on a step: a message may answer it

    def as_dict(self) -> dict[str, bool]:
        """For the audit log: the shape of the state, without what it is about."""
        return {
            "subject_open": self.subject is not None,
            "procedure": self.procedure is not None,
            "procedure_on_top": self.procedure_on_top,
        }


def act_of(reading: Reading, stack: ContextStack) -> Act:
    """The act a reading is, on the stack it was read on."""
    frame = stack.get(reading.frame_id) if reading.frame_id is not None else None
    if reading.action == "stop":
        return "stop"
    if reading.action == "new" or frame is None:
        return "new"
    if reading.action == "return":
        return "resume" if frame.procedure else "return"
    return "answer" if frame.procedure else "follow_up"


def reading_for(act: Act, stack: ContextStack) -> Reading | None:
    """The reading an act gives on this stack, when the act alone says which subject; None
    when it does not (back to which subject?), or leaves it to a reading that knows more (a
    step's answer is read against the step's options)."""
    top, procedure = stack.top, stack.procedure_frame()
    by = "classifier"
    if act == "new":
        return Reading("new", by=by)
    if act == "follow_up" and top is not None and not top.procedure:
        return Reading("continue", top.id, by=by)
    if act == "resume" and procedure is not None and procedure is not top:
        return Reading("return", procedure.id, by=by)
    if act == "stop" and procedure is not None:
        return Reading("stop", procedure.id, by=by)
    return None
