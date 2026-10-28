"""A scripted runner for tests and demos. Never touches Docker or the network."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from proving_ground.models import Scenario
from proving_ground.runner.base import PreflightResult, TrialSpec
from proving_ground.trial import TrialOutcome


class FakeRunner:
    def __init__(
        self,
        decide: Callable[[TrialSpec], str | tuple[str, int, int] | TrialOutcome],
        preflight: dict[str, PreflightResult] | None = None,
        cost_per_trial: float = 0.01,
        caps_cost: bool = False,
        free: bool = False,
    ):
        # caps_cost: like an agent that stops itself at TrialSpec.max_cost_usd (cut short: errored).
        self.caps_cost = caps_cost
        self.free = free
        self._decide = decide
        self._preflight = preflight or {}
        self._cost = cost_per_trial
        self.calls: list[TrialSpec] = []

    def preflight(self, scenario: Scenario, repo_root: Path) -> PreflightResult:
        return self._preflight.get(scenario.id, PreflightResult(scenario.id, True, False))

    def run_trial(self, spec: TrialSpec) -> TrialOutcome:
        self.calls.append(spec)
        result = self._decide(spec)
        if not isinstance(result, TrialOutcome):
            # ("fail", 11, 12): an outcome with partial credit, as a check's RIG_ITEMS line gives.
            outcome, right, total = result if isinstance(result, tuple) else (result, None, None)
            result = TrialOutcome(
                scenario_id=spec.scenario.id,
                kind=spec.scenario.kind,
                arm=spec.arm,
                repeat=spec.repeat,
                outcome=outcome,
                cost_usd=self._cost,
                items_right=right,
                items_total=total,
            )
        cap = spec.max_cost_usd
        if self.caps_cost and cap is not None and result.cost_usd > cap:
            result = replace(result, outcome="errored", cost_usd=cap)
        return result
