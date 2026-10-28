"""The Runner protocol the scheduler depends on."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from proving_ground.models import Scenario, Treatment
from proving_ground.trial import Arm, TrialOutcome


@dataclass(frozen=True)
class TrialSpec:
    experiment_id: int
    scenario: Scenario
    arm: Arm
    repeat: int
    treatment: Treatment
    model: str
    seed: int
    repo_root: Path
    # The most this trial may spend, for a runner whose agent can stop itself there (trial-budget).
    max_cost_usd: float | None = None


@dataclass(frozen=True)
class PreflightResult:
    scenario_id: str
    setup_ok: bool
    check_passed_without_agent: bool
    log: str = ""


class Runner(Protocol):
    # Optional: `free` (trials cost nothing) and `caps_cost` (honours TrialSpec.max_cost_usd).
    def preflight(self, scenario: Scenario, repo_root: Path) -> PreflightResult: ...

    def run_trial(self, spec: TrialSpec) -> TrialOutcome: ...
