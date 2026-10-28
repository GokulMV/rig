"""Two to four workflows on one bench: one after another, one shared baseline, one ranking.

The rules (how many, how the budget is split, when a winner may be named) are in
skills/judge-experiment (compare). This module holds the pure parts: the plan before a run, the
ranking, and the loop that runs each workflow in turn through injected functions, so it can be
tested without a sandbox.
"""

from __future__ import annotations

import math
import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from proving_ground import skills
from proving_ground.stats import wilson


def rule(key: str):
    return skills.value("judge-experiment", "compare")[key]


def share(budget: float, n: int) -> float:
    """Each workflow's budget: an even, fixed split (compare.split)."""
    if rule("split") != "even":
        raise ValueError(f"compare split must be even, not {rule('split')!r}")
    return budget / n if n else 0.0


# ---------- before a run: what each workflow is predicted to cost ----------


def plan(items: list[dict], pairs: int, budget: float) -> dict:
    """The trial-budget prediction for the whole set.

    `items`, in run order: {id, name, model, with_usd, without_usd, source} where the two costs
    are the budget check's per-trial prediction (margin included). The first workflow on a model
    pays for its "without" trials; later ones on that model reuse them (cost 0) for as many pairs
    as the earlier ones ran. Each workflow gets an even share and runs the pairs it pays for."""
    each = share(budget, len(items))
    baseline: dict[str, int] = {}  # model -> "without" pairs already paid for by an earlier run
    rows = []
    for it in items:
        shared = min(baseline.get(it["model"], 0), pairs)
        w, wo = float(it["with_usd"]), float(it["without_usd"])
        full = pairs * w + (pairs - shared) * wo
        afford, cost = 0, 0.0
        for k in range(pairs):
            c = w + (0.0 if k < shared else wo)
            if cost + c > each + 1e-9:
                break
            cost += c
            afford += 1
        baseline[it["model"]] = max(baseline.get(it["model"], 0), afford)
        rows.append(
            {
                "id": it["id"],
                "name": it["name"],
                "model": it["model"],
                "pairs": pairs,
                "pairs_in_budget": afford,
                "shared_baseline": min(shared, afford),
                "per_trial": {"with": round(w, 4), "without": round(wo, 4)},
                "source": it.get("source"),
                "budget": round(each, 4),
                "predicted_usd": round(full, 4),
                "predicted_in_budget": round(cost, 4),
                # What this one pays for "without" trials in full: 0 when it reuses them all.
                "baseline_usd": round((pairs - shared) * wo, 4),
            }
        )
    groups = len({it["model"] for it in items})
    return {
        "workflows": rows,
        "pairs": pairs,
        "budget": budget,
        "share": round(each, 4),
        "total_usd": round(sum(r["predicted_usd"] for r in rows), 4),
        "total_in_budget": round(sum(r["predicted_in_budget"] for r in rows), 4),
        "baselines": groups,  # how many baselines get paid for: one per session model
    }


def _usd(x: float) -> str:
    return f"${x:,.2f}"


def align_candidates(models: list[str]) -> list[str]:
    """The session models the set could all run on to share one baseline: the most common, in
    the order first pinned (`align_to`); more than one only when tied, and then the cheapest wins
    (see align)."""
    counts = Counter(models)
    top = max(counts.values(), default=0)
    return [m for m in dict.fromkeys(models) if counts[m] == top]


def align(now: dict, priced: dict[str, dict], label: Callable[[str], str] = str) -> dict | None:
    """When the set's workflows are on more than one session model: what the extra baselines
    cost and what running them all on one model would. `now` is the set's plan; `priced` maps each
    of align_candidates to the plan with every workflow on that model. None when one baseline is
    shared already."""
    if now["baselines"] < 2 or not priced:
        return None
    t = rule("text")
    target = min(priced, key=lambda m: (priced[m]["total_usd"], list(priced).index(m)))
    after = priced[target]
    extra = sum(r["baseline_usd"] for r in now["workflows"] if r["model"] != target)
    saving = round(now["total_usd"] - after["total_usd"], 4)
    total = _usd(after["total_usd"])
    if saving >= 0.005:
        result = t["align_saves"].format(total=total, usd=_usd(saving))
    elif saving <= -0.005:
        result = t["align_costs_more"].format(total=total, usd=_usd(-saving), model=label(target))
    else:
        result = t["align_level"].format(total=total)
    return {
        "model": target,
        "label": label(target),
        "models": list(dict.fromkeys(r["model"] for r in now["workflows"])),
        "extra_baseline_usd": round(extra, 4),
        "total_usd": after["total_usd"],
        "total_in_budget": after["total_in_budget"],
        "pairs_in_budget": sum(r["pairs_in_budget"] for r in after["workflows"]),
        "saving_usd": saving,
        "notice": t["models_notice"].format(n=now["baselines"], extra=_usd(extra)),
        "action": t["align_action"].format(model=label(target)),
        "result": result,
    }


# ---------- after a run: rank them, and never call a winner the intervals don't back ----------


def _measured(r: dict) -> bool:
    return (
        bool(r.get("valid"))
        and (r.get("n_pairs") or 0) > 0
        and r.get("ci_low") is not None
        and r.get("ci_high") is not None
        and r.get("diff") is not None
    )


def more_pairs(a: dict, b: dict) -> int | None:
    """About how many more pairs each would need before a's and b's intervals stop overlapping,
    if the gap between them holds; None when there is no gap (more pairs may never separate
    them). Each is {value, lo, hi, n} (or a ranked row: diff, ci_low, ci_high, n_pairs)."""
    a, b = _gauge(a), _gauge(b)
    d = abs(a["value"] - b["value"])
    if d < 1e-9:
        return None
    n = min(a["n"], b["n"])
    h = (a["hi"] - a["lo"]) / 2 + (b["hi"] - b["lo"]) / 2
    need = math.ceil(n * (h / d) ** 2 - 1e-9)  # 1e-9: float noise, not a pair
    return max(1, need - n)


def _gauge(r: dict) -> dict:
    if "value" in r:
        return r
    return {"value": r["diff"], "lo": r["ci_low"], "hi": r["ci_high"], "n": r["n_pairs"]}


def _pass_with(r: dict) -> dict:
    """The "with" arm's pass rate and its Wilson interval at the skill's confidence."""
    n = int(r["n_pairs"])
    x = min(n, max(0, round(float(r["pass_with"]) * n)))
    lo, hi = wilson(x, n, float(skills.value("judge-experiment", "z_confidence")))
    return {"value": x / n, "lo": lo, "hi": hi, "n": n}


def rank(rows: list[dict], label: Callable[[str], str] = str) -> dict:
    """`rows`: {id, name, rig (score or None), diff, ci_low, ci_high, n_pairs, valid}, and for
    ranking across models: model, pass_with, cost (the "with" arm's spend per trial).
    Measured on one session model: by Rig score, then the change. On more than one: by the pass
    rate with the workflow, then cost (rank_by_models), since each change is against its own
    model's baseline. Returns the order (measured ones only), what it was ranked by, each one's
    ranked figure, what each lift is against when across models (`label` names a model), the
    winner's id or None, and the sentence."""
    t = rule("text")
    measured = [r for r in rows if _measured(r)]
    models = list(dict.fromkeys(r["model"] for r in measured if r.get("model")))
    across = len(models) > 1
    if across:
        measured = [r for r in measured if r.get("pass_with") is not None]
        gauge = {r["id"]: _pass_with(r) for r in measured}
        cost = lambda r: r["cost"] if r.get("cost") is not None else math.inf  # noqa: E731
        order = sorted(
            measured,
            key=lambda r: (-round(gauge[r["id"]]["value"], 9), cost(r), -(r.get("rig") or -1)),
        )
    else:
        gauge = {r["id"]: _gauge(r) for r in measured}
        order = sorted(
            measured,
            key=lambda r: (-(r["rig"] if r.get("rig") is not None else -1), -r["diff"]),
        )
    out = {
        "order": [r["id"] for r in order],
        "by": "pass_with" if across else "rig",
        "by_text": t["by_models"].format(n=len(models)) if across else t["by_rig"],
        "models": models,
        "ranked": {
            k: {"value": round(g["value"], 4), "lo": round(g["lo"], 4), "hi": round(g["hi"], 4)}
            for k, g in gauge.items()
        },
        # Across models a lift is only against its own model's "without": say which, on each.
        "lift_vs": {
            r["id"]: t["lift_vs"].format(model=label(r["model"]))
            for r in rows
            if across and r.get("model")
        },
        "winner": None,
        "close": None,
        "more_pairs": None,
    }
    if len(order) < 2:
        return out | {"state": "too_few", "text": t["too_few"]}
    top, rest = order[0], order[1:]
    g = lambda r: gauge[r["id"]]  # noqa: E731
    if g(top)["lo"] > max(g(r)["hi"] for r in rest):
        return out | {
            "state": "winner",
            "winner": top["id"],
            "text": t["winner_models" if across else "winner"].format(name=top["name"]),
        }
    # The closest one whose interval reaches the top one's: the pair that can't be told apart.
    close = next(r for r in rest if g(r)["hi"] >= g(top)["lo"])
    n = more_pairs(g(top), g(close))
    cap = int(rule("more_pairs_cap"))
    if n is None:
        text = t["not_proven_level"].format(a=top["name"], b=close["name"])
    elif n > cap:
        text = t["not_proven_many"].format(a=top["name"], b=close["name"], n=cap)
    else:
        pairs = "pair" if n == 1 else "pairs"
        text = t["not_proven"].format(a=top["name"], b=close["name"], n=n, pairs=pairs)
    return out | {
        "state": "not_proven",
        "close": [top["id"], close["id"]],
        "more_pairs": n,
        "text": text,
    }


# ---------- the run: each workflow in turn ----------


class StartError(Exception):
    """A workflow couldn't start (its message is shown in its column)."""


@dataclass
class CompareJob:
    bench: str
    bench_name: str
    agent: str
    budget: float
    size: str
    rows: list[dict]  # {id, name, workflow, experiment, status, budget, spent, detail}
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    status: str = "running"  # running | stopping | done | stopped
    stop: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def active(self) -> bool:
        return self.status in ("running", "stopping")


def new_job(
    bench: str,
    bench_name: str,
    agent: str,
    budget: float,
    size: str,
    workflows: list[dict],
    models: list[str] | None = None,
) -> CompareJob:
    """`models`: each workflow's session model, recorded on its row so a page can tell a result
    from this run apart from the workflow as it is now."""
    lo, hi = int(rule("min")), int(rule("max"))
    if not lo <= len(workflows) <= hi:
        raise ValueError(f"Compare {lo} to {hi} workflows, not {len(workflows)}.")
    ids = [w["id"] for w in workflows]
    if len(set(ids)) != len(ids):
        raise ValueError("The same workflow is in the set twice.")
    return CompareJob(
        bench=bench,
        bench_name=bench_name,
        agent=agent,
        budget=budget,
        size=size,
        rows=[
            {
                "id": w["id"],
                "name": w["name"],
                "workflow": w,
                "experiment": None,
                "status": "queued",
                "budget": None,
                "spent": 0.0,
                "detail": None,
                "model": models[i] if models else None,
            }
            for i, w in enumerate(workflows)
        ],
    )


def drive(
    job: CompareJob,
    start: Callable[[dict, float], int],
    finished: Callable[[int], bool],
    spent: Callable[[int], float],
    stop_run: Callable[[int], None],
    error: Callable[[int], str | None] = lambda eid: None,
    poll_s: float = 0.05,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Run each workflow in order on the job's bench, each with an even share of the budget.
    `start(workflow, budget)` starts one run (reusing the shared baseline) and returns its
    experiment id, or raises StartError; the run is waited on until `finished`. Stopping stops
    the run in progress and skips the rest."""
    each = share(job.budget, len(job.rows))
    for i, row in enumerate(job.rows):
        if job.stop.is_set():
            with job.lock:
                for r in job.rows[i:]:
                    r["status"] = "skipped"
            break
        with job.lock:
            row["budget"] = round(each, 4)
        try:
            eid = start(row["workflow"], each)
        except StartError as e:
            with job.lock:
                row.update(status="error", detail=str(e))
            continue
        with job.lock:
            row.update(experiment=eid, status="running")
        while not finished(eid):
            if job.stop.is_set():
                stop_run(eid)
            sleep(poll_s)
        bad = error(eid)
        with job.lock:
            row["spent"] = round(spent(eid), 4)
            if bad:
                row.update(status="error", detail=bad)
            else:
                row["status"] = "stopped" if job.stop.is_set() else "done"
    with job.lock:
        job.status = "stopped" if job.stop.is_set() else "done"
