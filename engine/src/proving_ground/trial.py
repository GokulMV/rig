"""The outcome of one agent run in one arm."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from proving_ground.models import ScenarioKind

Arm = Literal["with", "without"]
Outcome = Literal["pass", "fail", "errored", "broken"]

# A fail whose detail starts with this: the agent ran out of the task's time limit (Harbor's
# AgentTimeoutError). It did not finish the task, so it is a fail, labelled "timed out".
TIMED_OUT = "timed out"


@dataclass(frozen=True)
class TrialOutcome:
    scenario_id: str
    kind: ScenarioKind
    arm: Arm
    repeat: int
    outcome: Outcome
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    duration_s: float = 0.0
    exit_code: int | None = None
    transcript_uri: str | None = None
    reused_from: int | None = None  # a baseline trial copied from this experiment
    # Partial credit: the check's last `RIG_ITEMS <right>/<total>` line (None: it printed none).
    items_right: int | None = None
    items_total: int | None = None
    # What happened beyond the outcome: "timed out after 600 s" for an agent timeout, the error
    # for an errored trial; None when there is nothing to add (or for a trial recorded before).
    detail: str | None = None

    @property
    def timed_out(self) -> bool:
        return self.outcome == "fail" and (self.detail or "").startswith(TIMED_OUT)
