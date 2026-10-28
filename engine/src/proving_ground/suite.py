"""One workflow across every bench that fits its discipline, with one pooled result.

The rules (which benches fit, how the budget is split, how pairs are pooled) are in
skills/judge-experiment. This module holds the pure parts: the job's shape and the pooling.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field, replace

from proving_ground import bench as bench_mod
from proving_ground import rig_score as rig_mod
from proving_ground import skills
from proving_ground.stats import summarize
from proving_ground.trial import TrialOutcome


def rule(key: str):
    return skills.value("judge-experiment", "suite")[key]


def fitting(discipline: str) -> list[bench_mod.Bench]:
    """Built-in benches that measure this discipline (imported and generated ones are skipped)."""
    return [
        b
        for b in bench_mod.benches()
        if discipline in b.disciplines and b.tasks is None and b.generated is None
    ]


def pool(per_bench: dict[str, list[TrialOutcome]]) -> dict:
    """The union of every bench's trials, task ids made unique per bench, summarized as one."""
    key = rule("scenario_key")
    union = [
        replace(t, scenario_id=key.format(bench=bid, scenario=t.scenario_id))
        for bid, trials in per_bench.items()
        for t in trials
    ]
    s = summarize(union)
    h = s.headline
    return {
        "verdict": s.verdict.value,
        "diff": h.diff if h else None,
        "ci_low": h.ci_low if h else None,
        "ci_high": h.ci_high if h else None,
        "n_pairs": h.n_pairs if h else 0,
        "pass_with": h.pass_with if h else None,
        "pass_without": h.pass_without if h else None,
    }


def pool_metric(per_bench: dict[str, tuple[list[TrialOutcome], object]], metric: str) -> dict | None:
    """The saving across benches (rig-score: Metric, Suites): each arm's total over every
    bench's pairs ÷ the tasks it solved in them, the bootstrap resampling each bench's pairs
    within that bench (`suite.pool_metric`). `per_bench`: bench → (its trials, its cost_of, for
    the cost a reused baseline trial ran at). None for the pass rate."""
    if not metric or metric == rig_mod.M["default"]:
        return None
    groups = [rig_mod.metric_rows(trials, metric, cost_of) for trials, cost_of in per_bench.values()]
    return rig_mod.metric_of_groups(metric, groups)


@dataclass
class SuiteJob:
    workflow: dict
    workflow_name: str
    agent: str
    budget: float
    size: str
    benches: list[dict]  # {bench, name, tasks, experiment, status, budget, spent, detail}
    metric: str = "pass_rate"  # what every bench's run, and the pooled result, is scored on
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    status: str = "running"  # running | stopping | done | stopped
    stop: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def active(self) -> bool:
        return self.status in ("running", "stopping")
