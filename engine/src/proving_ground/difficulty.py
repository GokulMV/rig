"""Is a bench too easy to show a lift? The agent alone's pass rate from trials already recorded.

Free: no model call, only the bench's own run records. Rules and values: the bench-difficulty
skill.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from proving_ground import skills
from proving_ground.baseline import meta
from proving_ground.budget import model_label
from proving_ground.store import Store

D = skills.load("bench-difficulty").values


def baseline(
    store: Store,
    root: Path,
    project_id: int,
    version: str,
    tasks: list[str],
    label: Callable[[str], str] = model_label,
) -> dict[str, dict]:
    """Per session model: the "without" trials run on this version of a tier (not reused, clean),
    how many passed, which of `tasks` they cover, and whether that makes the tier too easy.
    `label` names a model (the API's names a local model by its label)."""
    counts: dict[str, dict] = {}
    wanted = set(tasks)
    for e in store.list_experiments(project_id):
        if meta(root, e.id).get("bench_version") != version:
            continue
        for t in store.trials(e.id):
            if t.arm != "without" or t.reused_from is not None or t.outcome not in D["outcomes"]:
                continue
            if t.scenario_id not in wanted:
                continue
            c = counts.setdefault(e.model, {"passed": 0, "total": 0, "seen": set()})
            c["total"] += 1
            c["passed"] += t.outcome == "pass"
            c["seen"].add(t.scenario_id)
    return {
        m: verdict(m, c["passed"], c["total"], len(c["seen"]), len(wanted), label)
        for m, c in counts.items()
    }


def verdict(
    model: str,
    passed: int,
    total: int,
    seen: int,
    tasks: int,
    label: Callable[[str], str] = model_label,
) -> dict:
    """bench-difficulty's rule on one model's counts, with the sentence the Lab shows."""
    covered = seen >= tasks or not D["cover_every_task"]
    easy = total >= int(D["min_trials"]) and passed == total and covered
    words = {"model": label(model), "passed": passed, "total": total}
    return {
        "passed": passed,
        "total": total,
        "tasks_seen": seen,
        "tasks": tasks,
        "too_easy": easy,
        "model_label": label(model),
        "text": (D["too_easy"] if easy else D["measured"]).format(**words),
    }
