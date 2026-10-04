"""Per-feature tallies from an eval run: how often each check passed."""

from dataclasses import dataclass, field


@dataclass
class FeatureScore:
    feature_id: str
    total: int = 0
    routed: int = 0
    tool_called: int = 0
    text_present: int = 0
    cited: int = 0


@dataclass
class EvalReport:
    features: dict[str, FeatureScore] = field(default_factory=dict)
