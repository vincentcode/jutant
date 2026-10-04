"""Replays a pack's test questions to show whether a prompt or model change helped or hurt.

Reports per feature: correct feature routed, expected tool called, expected text present,
citation present. Run against fake adapters and the real model.
"""

from typing import TYPE_CHECKING

from core.evals.scoring import EvalReport
from core.packs.loader import Pack

if TYPE_CHECKING:
    from core.orchestrator.orchestrator import Orchestrator


async def run(pack: Pack, orchestrator: "Orchestrator") -> EvalReport:
    raise NotImplementedError
