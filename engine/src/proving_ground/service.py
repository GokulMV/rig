"""Set up and run an experiment. Shared by `pg run` and the API."""

from __future__ import annotations

import json
import math
import shutil
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from proving_ground import rig_score, validity
from proving_ground.baseline import env_fingerprint, reuse_without, source_cost
from proving_ground.beforeafter import Change
from proving_ground.budget import ARMS, CostModel, cap_record, history, prior_usd
from proving_ground.files import PG_DIR, load_scenarios
from proving_ground.models import (
    Scenario,
    ScenarioKind,
    Treatment,
    TreatmentKind,
    treatment_from_path,
)
from proving_ground.runner.harbor import HarborRunner
from proving_ground.sandbox.compiler import CompileOptions, UnsupportedFaultError, compile_task
from proving_ground.sandbox.snapshot import snapshot_repo, snapshot_rev
from proving_ground.sandbox.treatments import (
    instruction_compare,
    instruction_file,
    is_config,
    server_names,
)
from proving_ground.scheduler import Event, repeats_for, run_experiment
from proving_ground.stats import ResultSummary, Verdict, stop_verdict
from proving_ground.store import Store
from proving_ground.trial import Arm

DEFAULT_MODEL = "claude-sonnet-5-5"


class ServiceError(ValueError):
    """A request that cannot start. The message is meant for the user."""


@dataclass
class PreparedExperiment:
    eid: int
    root: Path
    store: Store
    runner: HarborRunner
    scenarios: list[Scenario]
    treatment: Treatment
    model: str
    repeats: int
    budget: float
    commit: str | None = None
    dirty: bool = False
    agent: str = "claude-code"
    # Auto-extend (judge-experiment skill): add pairs until the stricter interval decides.
    auto: dict | None = None
    # What the run is scored on (rig-score: Metric): auto-extend decides on it.
    metric: str | None = None
    # Shared baseline: re-run before each batch so new repeats reuse earlier "without" trials.
    bench_version: str | None = None
    env_fingerprint: str | None = None
    reuse_baseline: bool = True
    # The arms to run: both, or "without" alone for a baseline check (bench-difficulty: probe).
    arms: tuple[Arm, ...] = ARMS
    # Set to stop after the trial in progress (a running Docker trial isn't killed halfway).
    stop: threading.Event = field(default_factory=threading.Event)


def prepare_experiment(
    root: Path,
    treatment_path: Path | None,
    budget: float,
    n: int = 40,
    model: str = DEFAULT_MODEL,
    kinds: Sequence[ScenarioKind] = (),
    scenario_ids: Sequence[str] = (),
    resume: int | None = None,
    agent: str = "claude-code",
    env: dict[str, str] | None = None,
    extra_meta: dict | None = None,
    judge=None,
    harbor_model: str | None = None,  # the name the agent asks its server for, when not `model`
    free: bool = False,  # a local model: trials cost nothing
    ready_tasks: dict[str, Path] | None = None,  # imported Harbor tasks: copied, not compiled
    timeout_factor: float = 1.0,
    nudge: bool | None = None,  # tell the agent to open the treatment; None: workflows only
    reuse_baseline: bool = True,
    refuse: Callable[[], str | None] | None = None,  # a new run's last check, e.g. its budget
    arms: tuple[Arm, ...] = ARMS,
    change: Change | None = None,  # a code change before and after (beforeafter.resolve)
) -> PreparedExperiment:
    """Create (or reopen) the experiment, snapshot the repo and compile its tasks.

    With a `change`, there is no treatment folder: the "without" arm is the base commit's code
    and the "with" arm the after side's, each snapshotted from git and compiled on its own."""
    try:
        if change is not None:
            t = change.treatment(root)
        elif treatment_path is None:
            raise ValueError("Pick a change to measure.")
        else:
            t = treatment_from_path(treatment_path)
        items = load_scenarios(root)
    except (FileNotFoundError, ValueError) as e:
        raise ServiceError(str(e)) from e
    if ready_tasks is not None and (is_config(t) or change is not None):
        raise ServiceError(f"{t.kind.value} treatments cannot be used with imported Harbor tasks.")
    if (
        t.kind is TreatmentKind.INSTRUCTIONS
        and treatment_path is not None
        and instruction_compare(root, treatment_path) == "same"
    ):
        name = instruction_file(treatment_path).name
        raise ServiceError(
            f"Both arms would get the same {name}, so the run would measure nothing. Edit a copy "
            f"of it on Measure (or edit {name} without committing it), then measure that."
        )
    if kinds:
        items = [s for s in items if s.kind in kinds]
    if scenario_ids:
        items = [s for s in items if s.id in scenario_ids]
    if not items:
        raise ServiceError("No tasks match.")
    if broken := validity.broken_checks(items):  # evidence-validity: never pay for a broken check
        raise ServiceError(
            "These tasks' checks aren't commands, so every trial would fail both ways: "
            + "; ".join(f"{sid}: {why}" for sid, why in sorted(broken.items()))
            + " Fix their checks first, or leave them out of the run."
        )

    root = root.resolve()
    store = Store.for_project(root)
    pid = store.ensure_project(str(root))
    if resume is not None:
        try:
            e = store.get_experiment(resume)
        except KeyError as err:
            raise ServiceError(str(err.args[0])) from err
        if e.treatment_hash != t.content_hash:
            raise ServiceError(
                f"{t.name} changed since experiment {resume}. Start a new experiment instead."
            )
        eid, repeats, model = resume, e.repeats, e.model
    else:
        # After every check on the tasks (a broken check says more than a small budget), and
        # before anything is written.
        if refuse is not None and (why := refuse()) is not None:
            raise ServiceError(why)
        repeats = repeats_for(n, len(items))
        eid = store.create_experiment(pid, t, model, repeats, budget, seed=0)

    fingerprint = env_fingerprint(root, agent, harbor_model or model, env)
    exp_dir = root / PG_DIR / "runs" / str(eid)
    tasks_dir = exp_dir / "tasks"
    with_dir = exp_dir / "tasks-with"  # hook / MCP / instructions / before-after only
    with_dirs: dict[str, Path] | None = None
    two_trees = change is not None or is_config(t)  # the arms differ in files
    commit, dirty = None, False
    if resume is None or not tasks_dir.is_dir():
        after_snap = None
        if change is not None:  # each arm's code from git, never the live checkout
            assert change.base.sha is not None
            snap_path = snapshot_rev(root, change.base.sha, exp_dir / "snapshot")
            after_snap = snapshot_rev(root, change.after.sha or change.after.tree, exp_dir / "after")
            commit, dirty = change.base.sha, False
        else:
            snap = snapshot_repo(root, exp_dir / "snapshot")
            snap_path, commit, dirty = snap.path, snap.commit, snap.dirty
        (exp_dir / "meta.json").write_text(
            json.dumps(
                {"commit": commit, "dirty": dirty, "model": model, "agent": agent}
                | {"env_fingerprint": fingerprint, "nudge_prompt": nudge}
                | {"budget_cap": cap_record()}
                | ({"mcp_servers": server_names(t.path)} if t.kind is TreatmentKind.MCP else {})
                | ({"before_after": change.meta()} if change is not None else {})
                | (extra_meta or {}),
                indent=2,
            )
        )
        try:
            if ready_tasks is not None:
                task_dirs = {}
                for s in items:
                    shutil.copytree(ready_tasks[s.id], tasks_dir / s.id)
                    task_dirs[s.id] = tasks_dir / s.id
            else:
                opts = CompileOptions(agent_timeout_factor=timeout_factor)
                task_dirs = {
                    s.id: compile_task(
                        s, root, snap_path, tasks_dir / s.id, opts, agent=agent, treatment=t
                    )
                    for s in items
                }
                if two_trees:  # the arms differ in files: a second task folder for "with"
                    with_dirs = {
                        s.id: compile_task(
                            s,
                            root,
                            after_snap or snap_path,
                            with_dir / s.id,
                            opts,
                            agent=agent,
                            treatment=t,
                            arm="with",
                        )
                        for s in items
                    }
        except (UnsupportedFaultError, ValueError) as err:
            raise ServiceError(str(err)) from err
    else:
        task_dirs = {s.id: tasks_dir / s.id for s in items}
        if two_trees:
            with_dirs = {s.id: with_dir / s.id for s in items}

    if harbor_model is None:  # "" means the agent's own default
        harbor_model = model if "/" in model or agent != "claude-code" else f"anthropic/{model}"
    runner = HarborRunner(
        task_dirs,
        exp_dir / "trials",
        with_task_dirs=with_dirs,
        model=harbor_model or None,
        agent=agent,
        env=env,
        judge=judge,
        free=free,
        nudge=nudge,
        preflight_with=change is not None,
    )
    return PreparedExperiment(
        eid,
        root,
        store,
        runner,
        items,
        t,
        model,
        repeats,
        budget,
        commit,
        dirty,
        agent,
        bench_version=(extra_meta or {}).get("bench_version"),
        env_fingerprint=fingerprint,
        reuse_baseline=reuse_baseline,
        arms=arms,
        metric=(extra_meta or {}).get("metric"),
    )


def _reuse(p: PreparedExperiment, on_event: Callable[[Event], None]) -> None:
    if not p.bench_version or not p.reuse_baseline:
        return
    pid = p.store.get_experiment(p.eid).project_id
    r = reuse_without(
        p.store,
        p.root,
        pid,
        p.eid,
        p.scenarios,
        p.repeats,
        p.model,
        p.agent,
        p.bench_version,
        p.env_fingerprint,
    )
    if r.reused:
        on_event(
            {"type": "reused", "trials": r.reused, "saved_usd": r.saved_usd, "from": r.sources}
        )


def _costs(p: PreparedExperiment) -> CostModel:
    """What the next trial is predicted to cost (trial-budget): this run, this bench, the prior."""
    return CostModel(
        prior_usd(p.model),
        history(p.store, p.root, p.eid, p.model, p.agent),
        free=p.runner.free,
    )


def _saving(p: PreparedExperiment) -> bool:
    return bool(p.metric) and p.metric != rig_score.M["default"]


def extend_steps(a: dict, tasks: int, saving: bool) -> tuple[int, int, int]:
    """(repeats a look adds, most looks, most pairs) for auto-extend (judge-experiment:
    auto_extend): on a saving a look adds at least `metric.step_pairs` pairs."""
    step, looks, cap = a["step_repeats"], a["max_looks"], a["max_pairs"]
    if saving:
        caps = a["metric"]
        step = max(step, math.ceil(caps["step_pairs"] / max(tasks, 1)))
        looks, cap = caps["max_looks"], caps["max_pairs"]
    return step, looks, cap


def extend_ceiling(a: dict, planned: int, tasks: int, saving: bool) -> int:
    """The most pairs a run planned at `planned` pairs over `tasks` tasks can grow to while it is
    undecided, before the budget: every look's pairs complete and it is never decided. It is
    what execute's caps allow, so a free run (a local model) stops there at the latest."""
    step, looks, cap = extend_steps(a, tasks, saving)
    per = step * tasks
    if per <= 0 or planned + per > cap:
        return planned
    return planned + per * min(looks, (cap - planned) // per)


def extend_plan(
    a: dict, planned: int, tasks: int, saving: bool, per_pair: float, budget: float | None
) -> dict:
    """Before a run with auto-extend on: the most pairs it may grow to (extend_ceiling), what
    those cost, the pairs the budget stops it at, and the line the estimate and confirm say
    (judge-experiment: auto_extend text.grows). `per_pair` 0: free, so the caps alone stop it."""
    t = a["text"]["grows"]
    most = extend_ceiling(a, planned, tasks, saving)
    free = per_pair <= 0
    reach = most if free or budget is None else min(most, int((budget + 1e-9) // per_pair))
    usd = None if free else round(per_pair * most, 2)

    def n(k: int) -> str:
        return f"{k} pair" if k == 1 else f"{k} pairs"

    stop = "the budget" if budget is None else f"${budget:.2f}"
    if most <= planned:
        line = t["none"].format(pairs=n(planned))
    elif free:
        line = t["free"].format(pairs=n(most))
    elif reach <= planned:
        line = t["no_budget"].format(pairs=n(planned), budget=stop)
    elif reach < most:
        line = t["budget"].format(pairs=n(reach), most=n(most), budget=stop)
    else:
        line = t["paid"].format(pairs=n(most), usd=f"${usd:.2f}", budget=stop)
    return {"max_pairs": most, "usd": usd, "pairs_in_budget": reach, "line": line}


def _decided(p: PreparedExperiment, a: dict) -> tuple[str | None, int, str | None]:
    """(why it is decided, or None; the pairs; on a saving, what it still waits for). The pass
    rate: the stricter interval excludes zero. A saving: rig_score.metric_stop."""
    trials = p.store.trials(p.eid)
    if not _saving(p):
        decided, pairs = stop_verdict(trials, a["stop_z"])
        if decided is Verdict.INCONCLUSIVE:
            return None, pairs, None
        return f"decided at the stricter interval ({decided.value})", pairs, None
    st = rig_score.metric_stop(trials, p.metric, a["stop_z"], source_cost(p.store))
    t = a["text"]
    kw = {
        "name": rig_score.M["names"][p.metric].lower(),
        "noun": rig_score.M["nouns"][p.metric],
        "small": f"{rig_score.M['doesnt_below_cut'] * 100:.0f}",
    }
    if st["why"]:
        return t["decided"][st["why"]].format(**kw), st["pairs"], None
    w = st["waiting"]
    return None, st["pairs"], t["waiting"]["both" if len(w) == 2 else w[0]]


def execute(p: PreparedExperiment, on_event: Callable[[Event], None]) -> ResultSummary:
    """Run every pending trial; with auto-extend, keep adding pairs until it is decided (on a
    saving: the saving and its guard, judge-experiment: Auto-extend). Raises the scheduler's and
    runner's errors unchanged."""
    _reuse(p, on_event)
    summary = run_experiment(
        p.store,
        p.runner,
        p.eid,
        p.scenarios,
        p.treatment,
        p.root,
        p.model,
        0,
        p.repeats,
        p.budget,
        on_event=on_event,
        should_stop=p.stop.is_set,
        cost_model=_costs(p),
        arms=p.arms,
    )
    if not p.auto:
        return summary
    a = p.auto
    step, looks, cap = extend_steps(a, len(p.scenarios), _saving(p))

    def unsettled(reason: str, waiting: str | None) -> str:
        return a["text"]["undecided"].format(reason=reason, waiting=waiting) if waiting else reason

    for look in range(looks):
        status = p.store.get_experiment(p.eid).status
        why, pairs, waiting = _decided(p, a)
        spent = p.store.spent(p.eid)
        reason = None
        if p.stop.is_set() or status == "stopped":
            return summary
        if why is not None:
            reason = why
        elif status == "stopped_budget" or spent >= p.budget:
            reason = unsettled("the budget can't pay for another pair", waiting)
        elif pairs + step * len(p.scenarios) > cap:
            reason = unsettled(f"reached {pairs} pairs", waiting)
        if reason:
            on_event({"type": "settled", "reason": reason, "pairs": pairs, "looks": look})
            return summary
        p.repeats += step
        p.store.set_repeats(p.eid, p.repeats)
        on_event(
            {"type": "extended", "repeats": p.repeats, "pairs": pairs, "look": look + 1}
            | ({"waiting": waiting} if waiting else {})
        )
        _reuse(p, on_event)
        summary = run_experiment(
            p.store,
            p.runner,
            p.eid,
            p.scenarios,
            p.treatment,
            p.root,
            p.model,
            0,
            p.repeats,
            p.budget,
            on_event=on_event,
            should_stop=p.stop.is_set,
            cost_model=_costs(p),
            arms=p.arms,
        )
        if p.stop.is_set():
            return summary
    reason = f"{looks} extra looks"
    pairs = summary.headline.n_pairs if summary.headline else 0
    # The last batch may have decided it; else say the cap, and on a saving what it didn't.
    why, at, waiting = _decided(p, a)
    if why is not None:
        reason, pairs = why, at
    elif _saving(p):
        reason, pairs = unsettled(reason, waiting), at
    on_event({"type": "settled", "reason": reason, "pairs": pairs, "looks": looks})
    return summary
