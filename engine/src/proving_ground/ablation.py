"""Slim this workflow: leave-one-out variants of a workflow, a job that measures them one after
another, and what each part contributes. No model calls of its own.

Rules and values live in the ablation skill.
"""

from __future__ import annotations

import copy
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from proving_ground import lab, skills

A = skills.load("ablation").values
POINTS = 100  # results are fractions; contributions are in points


@dataclass
class Variant:
    key: str  # the step id; "loop:<from>:<to>" for a loop; "model:<step id>" for a cheaper model
    kind: str  # drop | loop | model
    label: str
    workflow: lab.Workflow


def _short(model: str) -> str:
    return lab.W["models"].get(model, {}).get("label", model)


def _drop(wf: lab.Workflow, sid: str) -> lab.Workflow:
    """Without a step: everything that led into it now leads to everything that followed it, and
    loops through it go. (If that leaves no edges at all, the steps run in order, as in any
    workflow with no edges.)"""
    v = copy.deepcopy(wf)
    before = [a for a, b in v.edges if b == sid]
    after = [b for a, b in v.edges if a == sid]
    keep = [e for e in v.edges if sid not in e[:2]]
    for a in before:
        for b in after:
            if a != b and [a, b] not in keep:
                keep.append([a, b])
    v.steps = [st for st in v.steps if st.id != sid]
    v.edges = keep
    v.loops = [lp for lp in v.loops if sid not in lp[:2]]
    v.loop = None
    return lab._price(lab.normalize(v))


def _derive(wf: lab.Workflow, v: lab.Workflow, label: str) -> lab.Workflow:
    v.id = lab._wid(wf.id, label)
    return v


def plan(wf: lab.Workflow) -> list[Variant]:
    """Every variant, uncapped: drop-step first, then loops, then cheaper models."""
    out: list[Variant] = []
    do_steps = [st for st in wf.steps if st.kind == "do"]
    if len(wf.steps) > 1:
        for st in wf.steps:
            if st.kind == "do" and len(do_steps) == 1:
                continue
            label = f"Without {st.name}"
            v = _derive(wf, _drop(wf, st.id), label)
            v.name = f"{wf.name} − {st.name}"
            out.append(Variant(st.id, "drop", label, v))
    names = {st.id: st.name for st in wf.steps}
    for frm, to, _mx in wf.loops:
        label = f"Without the loop {names.get(frm, frm)} → {names.get(to, to)}"
        v = copy.deepcopy(wf)
        v.loops = [lp for lp in v.loops if lp[:2] != [frm, to]]
        v.loop = None
        v = _derive(wf, lab._price(lab.normalize(v)), label)
        v.name = f"{wf.name} − loop {names.get(frm, frm)} → {names.get(to, to)}"
        out.append(Variant(f"loop:{frm}:{to}", "loop", label, v))
    for st in wf.steps:
        rule = A["downgrade"].get(st.model)
        if rule is None or st.kind not in rule["kinds"]:
            continue
        label = f"{st.name} on {_short(rule['to'])}"
        v = copy.deepcopy(wf)
        for s2 in v.steps:
            if s2.id == st.id:
                s2.model = rule["to"]
        v = _derive(wf, lab._price(lab.normalize(v)), label)
        v.name = f"{wf.name} − {st.name} ({_short(rule['to'])})"
        out.append(Variant(f"model:{st.id}", "model", label, v))
    return out


def planned(wf: lab.Workflow) -> list[Variant]:
    """The variants a job runs: at most max_variants, drop-step ones chosen first."""
    return plan(wf)[: A["max_variants"]]


def variants(wf: lab.Workflow) -> list[tuple[str, lab.Workflow]]:
    """(label, workflow) for each variant a job would run."""
    return [(v.label, v.workflow) for v in planned(wf)]


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    """How much of the narrower interval the other covers, 0 to 1."""
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    if hi < lo:
        return 0.0
    narrow = min(a[1] - a[0], b[1] - b[0])
    return 1.0 if narrow <= 0 else min(1.0, (hi - lo) / narrow)


def _cost_per_task(row: dict) -> float | None:
    w = (row.get("costs") or {}).get("with") or {}
    return w["spent_usd"] / w["tasks"] if w.get("tasks") else None


def contributions(parent_row: dict, variant_rows: list[dict]) -> dict[str, dict]:
    """What each part contributes. Each variant row is a result row (diff, ci_low, ci_high, costs)
    with `key` (see Variant) and `kind`. marginal_pts is the workflow's difference minus the
    variant's; saved_cost_usd is what the variant saves per task."""
    x = A["min_points"]
    out: dict[str, dict] = {}
    pd = parent_row.get("diff")
    pcost = _cost_per_task(parent_row)
    for r in variant_rows:
        vd = r.get("diff")
        if pd is None or vd is None:
            out[r["key"]] = {
                "kind": r.get("kind", "drop"),
                "marginal_pts": None,
                "saved_cost_usd": None,
                "verdict": "unclear",
            }
            continue
        marginal = (pd - vd) * POINTS
        vcost = _cost_per_task(r)
        saved = pcost - vcost if pcost is not None and vcost is not None else None
        cheaper = saved is not None and pcost and saved >= A["min_saving"] * pcost
        have = all(r.get(k) is not None for k in ("ci_low", "ci_high")) and all(
            parent_row.get(k) is not None for k in ("ci_low", "ci_high")
        )
        overlap = (
            _overlap(
                (parent_row["ci_low"], parent_row["ci_high"]),
                (r["ci_low"], r["ci_high"]),
            )
            if have
            else 1.0
        )
        if abs(marginal) < x:
            verdict = "dead weight" if cheaper else "neutral"
        elif overlap > A["unclear_overlap"]:
            verdict = "unclear"
        else:
            verdict = "essential" if marginal > 0 else "harmful"
        out[r["key"]] = {
            "kind": r.get("kind", "drop"),
            "marginal_pts": round(marginal, 1),
            "saved_cost_usd": None if saved is None else round(saved, 4),
            "verdict": verdict,
        }
    return out


@dataclass
class Job:
    id: str
    parent: str  # the workflow's id
    bench: str
    budget: float
    agent: str
    parent_eid: int | None = None  # the measured run the variants are compared with
    variants: list[dict] = field(default_factory=list)
    status: str = "running"  # running | done | stopped
    spent: float = 0.0
    note: str = ""
    stop: threading.Event = field(default_factory=threading.Event)

    def dump(self) -> dict:
        return {
            "id": self.id,
            "workflow": self.parent,
            "bench": self.bench,
            "budget": self.budget,
            "agent": self.agent,
            "parent_experiment": self.parent_eid,
            "status": self.status,
            "spent_usd": round(self.spent, 4),
            "note": self.note,
            "variants": [{k: v for k, v in x.items() if k != "wf"} for x in self.variants],
        }


class Jobs:
    """Ablation jobs, in memory. A job measures its variants one after another through
    `start` (the same machinery as a Lab run)."""

    def __init__(
        self,
        start: Callable[[dict], dict],
        finished: Callable[[str, int], bool],
        spent: Callable[[str, int], float],
        stop_run: Callable[[str, int], bool],
        busy: Callable[[], int | None],
        poll: float = 0.1,
    ) -> None:
        self._start, self._finished, self._spent = start, finished, spent
        self._stop_run, self._busy, self._poll = stop_run, busy, poll
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def running(self) -> Job | None:
        with self._lock:
            return next((j for j in self.jobs.values() if j.status == "running"), None)

    def create(
        self,
        wf: lab.Workflow,
        bench: str,
        budget: float,
        agent: str,
        parent_eid: int | None = None,
        **run_args,
    ) -> Job:
        chosen = planned(wf)
        if not chosen:
            raise ValueError("There is nothing to take out of this workflow.")
        job = Job(uuid.uuid4().hex[:10], wf.id, bench, budget, agent, parent_eid)
        job.variants = [
            {
                "key": v.key,
                "kind": v.kind,
                "label": v.label,
                "workflow_id": v.workflow.id,
                "experiment_id": None,
                "status": "pending",
                "detail": "",
                "wf": v.workflow,
            }
            for v in chosen
        ]
        with self._lock:
            self.jobs[job.id] = job
        threading.Thread(target=self._work, args=(job, run_args), daemon=True).start()
        return job

    def stop(self, jid: str) -> bool:
        job = self.jobs.get(jid)
        if job is None or job.status != "running":
            return False
        job.stop.set()
        for v in job.variants:
            if v["status"] == "running" and v["experiment_id"] is not None:
                self._stop_run(job.bench, v["experiment_id"])
        return True

    def _work(self, job: Job, run_args: dict) -> None:
        todo = len(job.variants)
        for i, v in enumerate(job.variants):
            if job.stop.is_set():
                break
            share = (job.budget - job.spent) / (todo - i)
            if share < 0.01:
                job.note = "The budget ran out before every variant was measured."
                break
            try:
                self._run_one(job, v, share, run_args)
            except Exception as e:  # noqa: BLE001 - one variant failing must not lose the others
                v["status"], v["detail"] = "error", getattr(e, "detail", None) or str(e)
        for v in job.variants:
            if v["status"] == "pending":
                v["status"] = "skipped"
        job.status = "stopped" if job.stop.is_set() else "done"

    def _run_one(self, job: Job, v: dict, share: float, run_args: dict) -> None:
        started = None
        for _ in range(600):  # another run may hold the lab for a while: wait for it
            if job.stop.is_set():
                return
            if self._busy() is None:
                try:
                    started = self._start(
                        {
                            **run_args,
                            "workflow": v["wf"].dump(),
                            "bench": job.bench,
                            "budget": share,
                            "agent": job.agent,
                        }
                    )
                    break
                except Exception as e:  # noqa: BLE001
                    if getattr(e, "status_code", None) != 409:
                        raise
            time.sleep(self._poll)
        if started is None:
            raise RuntimeError("The lab stayed busy.")
        v["experiment_id"], v["status"] = started["id"], "running"
        if job.stop.is_set():  # stop() came in between starting the run and noting it
            self._stop_run(job.bench, started["id"])
        while not self._finished(job.bench, started["id"]):
            time.sleep(self._poll)
        job.spent += self._spent(job.bench, started["id"])
        v["status"] = "stopped" if job.stop.is_set() else "done"
