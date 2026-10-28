"""Paired with/without experiment scheduling with preflight, a budget cap and resume."""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path

from proving_ground.budget import ARMS, CostModel, Ledger, Reservation, evidence, prior_usd
from proving_ground.models import Scenario, Treatment
from proving_ground.runner.base import PreflightResult, Runner, TrialSpec
from proving_ground.stats import ResultSummary, summarize
from proving_ground.store import Store
from proving_ground.trial import Arm, TrialOutcome

Event = dict


class NotRunnableError(Exception):
    def __init__(self, ids: list[str]):
        super().__init__(f"tasks need an approved check before running: {', '.join(ids)}")
        self.ids = ids


class PreflightError(Exception):
    def __init__(self, results: list[PreflightResult]):
        ids = ", ".join(r.scenario_id for r in results)
        super().__init__(f"checks pass with no agent, so they test nothing: {ids}")
        self.results = results


def repeats_for(n_per_arm: int, n_scenarios: int) -> int:
    if n_scenarios <= 0:
        raise ValueError("need at least one scenario")
    return math.ceil(n_per_arm / n_scenarios)


def plan_trials(
    scenarios: list[Scenario], repeats: int, only: tuple[Arm, ...] = ARMS
) -> list[tuple[Scenario, int, Arm]]:
    """Every trial in order, the arms alternating first by repeat; `only`: run just these arms
    (a baseline check runs "without" alone: bench-difficulty)."""
    out: list[tuple[Scenario, int, Arm]] = []
    for r in range(repeats):
        arms: tuple[Arm, Arm] = ("with", "without") if r % 2 == 0 else ("without", "with")
        for s in scenarios:
            for arm in arms:
                if arm in only:
                    out.append((s, r, arm))
    return out


def run_experiment(
    store: Store,
    runner: Runner,
    experiment_id: int,
    scenarios: list[Scenario],
    treatment: Treatment,
    repo_root: Path,
    model: str,
    seed: int,
    repeats: int,
    budget_usd: float,
    on_event: Callable[[Event], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    cost_model: CostModel | None = None,
    arms: tuple[Arm, ...] = ARMS,
) -> ResultSummary:
    emit = on_event or (lambda e: None)
    if not scenarios:
        raise ValueError("need at least one scenario")
    not_ready = [s.id for s in scenarios if not s.runnable]
    if not_ready:
        raise NotRunnableError(not_ready)

    pre = [runner.preflight(s, repo_root) for s in scenarios]
    vacuous = [p for p in pre if p.setup_ok and p.check_passed_without_agent]
    if vacuous:
        store.set_status(experiment_id, "failed_preflight")
        raise PreflightError(vacuous)

    done = store.done_keys(experiment_id)
    broken = {p.scenario_id: p for p in pre if not p.setup_ok}
    for s in scenarios:
        if s.id not in broken:
            continue
        for arm in arms:
            if (s.id, arm, 0) not in done:
                store.record_trial(experiment_id, TrialOutcome(s.id, s.kind, arm, 0, "broken"))
        emit({"type": "broken", "scenario_id": s.id, "log": broken[s.id].log})

    store.set_status(experiment_id, "running")
    # The budget is a cap (trial-budget): a pair starts only when what it is predicted to cost
    # fits next to what is spent and reserved; a trial starts only when nothing overspent it.
    ledger = Ledger(budget_usd, store.spent(experiment_id))
    costs = cost_model or CostModel(prior_usd(model), free=bool(getattr(runner, "free", False)))
    caps = bool(getattr(runner, "caps_cost", False))
    seen = evidence(store.trials(experiment_id))
    held: dict[tuple[str, int, Arm], Reservation] = {}

    def stop_budget(predicted: float, left: float, reason: str) -> None:
        for r in held.values():
            ledger.release(r)
        store.set_status(experiment_id, "stopped_budget")
        emit(
            {
                "type": "stopped_budget",
                "spent_usd": ledger.spent,
                "predicted_usd": round(predicted, 4),
                "left_usd": round(max(0.0, left), 4),
                "reason": reason,
            }
        )

    runnable = [s for s in scenarios if s.id not in broken]
    for s, rep, arm in plan_trials(runnable, repeats, arms):
        if (s.id, arm, rep) in done:
            continue
        if should_stop and should_stop():  # asked to stop: after the trial that was running
            for r in held.values():
                ledger.release(r)
            store.set_status(experiment_id, "stopped")
            emit({"type": "stopped", "spent_usd": ledger.spent})
            break
        if (s.id, rep, arm) not in held:  # the first arm of its pair still to run
            todo = [a for a in arms if (s.id, a, rep) not in done]
            guesses = [costs.estimate(a, seen[a]) for a in todo]
            need = sum(g for g, _ in guesses)
            got = ledger.reserve([g for g, _ in guesses])
            if got is None:
                left = ledger.free()
                src = "; ".join(dict.fromkeys(src for _, src in guesses))
                what = "pair" if len(todo) == 2 else f"{todo[0]!r} trial"
                stop_budget(
                    need,
                    left,
                    f"the next {what} would cost about ${need:.2f} ({src}); "
                    f"${max(0.0, left):.2f} left",
                )
                break
            held.update({(s.id, rep, a): r for a, r in zip(todo, got, strict=True)})
        r = held.pop((s.id, rep, arm))
        if not ledger.fits(r):  # its pair's first trial cost more than predicted
            left = ledger.free() + r.amount
            stop_budget(
                r.amount,
                left,
                f"the {arm!r} trial would cost about ${r.amount:.2f}; ${max(0.0, left):.2f} "
                "left after the trial before it cost more than predicted",
            )
            break
        cap = ledger.claim(r) if caps and not costs.free else None
        try:
            outcome = runner.run_trial(
                TrialSpec(
                    experiment_id, s, arm, rep, treatment, model, seed, repo_root, max_cost_usd=cap
                )
            )
        except BaseException:
            ledger.release(r)
            raise
        store.record_trial(experiment_id, outcome)
        ledger.settle(r, outcome.cost_usd)
        if outcome.reused_from is None and outcome.cost_usd > 0:
            seen[arm].append(outcome.cost_usd)
        emit(
            {
                "type": "trial",
                "scenario_id": s.id,
                "arm": arm,
                "repeat": rep,
                "outcome": outcome.outcome,
                "timed_out": outcome.timed_out,
                "spent_usd": ledger.spent,
            }
        )
    else:
        store.set_status(experiment_id, "done")
        emit({"type": "done", "spent_usd": ledger.spent})
    return summarize(store.trials(experiment_id))
