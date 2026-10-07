"""The stack of frames, top first, and how it is kept between turns (as plain data)."""

from dataclasses import dataclass, field, replace
from typing import Any

MAX_FRAMES = 5
STALE_TURNS = 20  # a frame untouched this long is dropped
KEPT_EXCHANGES = 3  # per frame: the model sees the subject's last few questions and answers
ANSWER_CHARS = 600


@dataclass(frozen=True)
class Frame:
    id: int
    feature_id: str
    entities: dict[str, str] = field(default_factory=dict)  # type -> id, the current one
    procedure: bool = False  # holds the conversation's procedure run
    exchanges: tuple[tuple[str, str], ...] = ()  # (question, answer), oldest first
    touched: int = 0  # the turn it was last active
    # What its records point to (a transfer's failure code): not what the subject is about, so
    # not used for its own lookups, but passed to a question about the same case.
    related: dict[str, str] = field(default_factory=dict)

    def with_entities(self, found: dict[str, str]) -> "Frame":
        return replace(self, entities={**self.entities, **found}) if found else self

    def with_related(self, found: dict[str, str]) -> "Frame":
        return replace(self, related={**self.related, **found}) if found else self

    def with_exchange(self, question: str, answer: str) -> "Frame":
        kept = (*self.exchanges, (question, answer[:ANSWER_CHARS]))[-KEPT_EXCHANGES:]
        return replace(self, exchanges=kept)


MAX_NAMES = 50


@dataclass
class ContextStack:
    frames: list[Frame] = field(default_factory=list)  # top first
    turn: int = 0
    next_id: int = 1
    # Names learned from tool results: lower-case name -> (type, id). "standard savings" ->
    # ("product", "SAV-STD").
    names: dict[str, tuple[str, str]] = field(default_factory=dict)

    def learn(self, names: dict[str, tuple[str, str]]) -> None:
        self.names = dict(list({**self.names, **names}.items())[-MAX_NAMES:])

    def name_of(self, kind: str, value: str) -> str | None:
        """A name learned for this entity (kept in lower case, for matching)."""
        return next((n for n, (k, v) in self.names.items() if k == kind and v == value), None)

    @property
    def top(self) -> Frame | None:
        return self.frames[0] if self.frames else None

    def get(self, frame_id: int) -> Frame | None:
        return next((f for f in self.frames if f.id == frame_id), None)

    def procedure_frame(self) -> Frame | None:
        return next((f for f in self.frames if f.procedure), None)

    def holding(self, entity_type: str, entity_id: str) -> Frame | None:
        """The most recent frame about this entity."""
        return next((f for f in self.frames if f.entities.get(entity_type) == entity_id), None)

    def push(
        self, feature_id: str, entities: dict[str, str] | None = None, procedure: bool = False
    ) -> Frame:
        frame = Frame(self.next_id, feature_id, dict(entities or {}), procedure, (), self.turn)
        self.next_id += 1
        self.frames.insert(0, frame)
        self._prune()
        return frame

    def bring_to_top(self, frame_id: int) -> Frame:
        frame = self.get(frame_id)
        assert frame is not None, frame_id
        self.frames.remove(frame)
        frame = replace(frame, touched=self.turn)
        self.frames.insert(0, frame)
        return frame

    def put(self, frame: Frame) -> None:
        """Replace the frame with the same id (it keeps its place)."""
        self.frames = [frame if f.id == frame.id else f for f in self.frames]

    def drop(self, frame_id: int) -> None:
        self.frames = [f for f in self.frames if f.id != frame_id]

    def _prune(self) -> None:
        fresh = [f for f in self.frames if self.turn - f.touched <= STALE_TURNS]
        self.frames = fresh[:MAX_FRAMES]

    def as_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "next_id": self.next_id,
            "names": {name: list(entity) for name, entity in self.names.items()},
            "frames": [
                {
                    "id": f.id,
                    "feature_id": f.feature_id,
                    "entities": f.entities,
                    "procedure": f.procedure,
                    "exchanges": [list(e) for e in f.exchanges],
                    "touched": f.touched,
                    "related": f.related,
                }
                for f in self.frames
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ContextStack":
        if not data:
            return cls()
        frames = [
            Frame(
                int(f["id"]),
                str(f["feature_id"]),
                {str(k): str(v) for k, v in (f.get("entities") or {}).items()},
                bool(f.get("procedure")),
                tuple((str(q), str(a)) for q, a in f.get("exchanges") or ()),
                int(f.get("touched", 0)),
                {str(k): str(v) for k, v in (f.get("related") or {}).items()},
            )
            for f in data.get("frames") or ()
        ]
        names = {str(n): (str(e[0]), str(e[1])) for n, e in (data.get("names") or {}).items()}
        return cls(
            frames, int(data.get("turn", 0)), int(data.get("next_id", len(frames) + 1)), names
        )
