"""`pg gate`: measure one skill or workflow on a bench and turn the result into a pass or fail.

Exit codes: 0 passed, 1 failed (it hurts, or falls under a threshold), 2 undecided (the budget
ran out first, or the sandbox, sign-in or bench broke).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from proving_ground import adherence
from proving_ground import bench as bench_mod
from proving_ground import local_models as local_mod
from proving_ground import rig_score as rig_mod
from proving_ground.agents import Credentials, agent
from proving_ground.baseline import meta as run_meta
from proving_ground.baseline import source_cost
from proving_ground.report import metric_rig
from proving_ground.runner.harbor import AgentAuthError
from proving_ground.scheduler import Event, NotRunnableError, PreflightError
from proving_ground.service import DEFAULT_MODEL, ServiceError, execute, prepare_experiment
from proving_ground.stats import Verdict, summarize

HOME = Path.home() / ".proving-ground"
FORMATS = ("text", "github-md", "junit")
PASS, FAIL, UNDECIDED = 0, 1, 2


def trial_count(b: bench_mod.Bench, size: str) -> int:
    """Cases per arm: a pilot is one per scenario, a full run at least 20."""
    return size_count(len(b.scenarios), size)


def size_count(tasks: int, size: str) -> int:
    """trial_count for `tasks` scenarios: a pilot is one each, a full run at least 20 (before it
    grows with the budget: budget.full_pairs)."""
    return tasks if size == "pilot" else max(20, tasks)


def session_model(models: list[str]) -> str:
    """The model most of the work runs on (a workflow's steps may each use their own). A tie
    goes to the earliest step's model, so the same workflow always runs (and is priced) on one."""
    return max(models, key=models.count)


def use_home(home: Path) -> None:
    """Point the bench registry at a Rig home (imported and generated benches)."""
    bench_mod.IMPORTS = home / "imported-benches.json"
    bench_mod.GENERATED = home / "generated-benches"


@dataclass
class ScenarioRow:
    id: str
    with_pass: int
    with_total: int
    without_pass: int
    without_total: int

    @property
    def rate_with(self) -> float | None:
        return self.with_pass / self.with_total if self.with_total else None

    @property
    def rate_without(self) -> float | None:
        return self.without_pass / self.without_total if self.without_total else None

    @property
    def ok(self) -> bool:
        a, b = self.rate_with, self.rate_without
        return a is not None and (b is None or a >= b)


@dataclass
class GateResult:
    code: int
    treatment: str
    bench: str
    agent: str
    model: str
    thresholds: dict
    verdict: str | None = None
    diff: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    pairs: int = 0
    spent_usd: float = 0.0
    status: str | None = None
    adherence: dict | None = None  # {"followed": n, "read": n}
    scenarios: list[ScenarioRow] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)  # why it failed or is undecided
    warnings: list[str] = field(default_factory=list)
    # What it is scored on (rig-score: Metric). On tokens, cost or time: the saving's headline,
    # the pass rate as its guard, and the verdict on the metric ({id, word, reason}).
    metric: str = "pass_rate"
    headline: str | None = None
    guard: str | None = None
    metric_verdict: dict | None = None

    @property
    def label(self) -> str:
        return {PASS: "PASS", FAIL: "FAIL", UNDECIDED: "UNDECIDED"}[self.code]


def decide(
    r: GateResult, min_delta: float, min_adherence: float, budget_stopped: bool
) -> GateResult:
    """Fill in r.code and r.reasons from its measured numbers. Scored on tokens, cost or time,
    the verdict on the metric decides (its pass-rate guard included): "Helps" passes, "Doesn't
    Help" fails, "Can't Tell Yet" is undecided; --min-delta is the pass rate's, so it is not
    used there. Adherence is checked either way."""
    if r.metric_verdict is not None and r.diff is not None:
        return _decide_metric(r, min_adherence, budget_stopped)
    if r.diff is None or r.verdict is None:
        r.code = UNDECIDED
        r.reasons.append("No complete with/without pairs, so there is nothing to judge.")
        return r
    pts = r.diff * 100
    if r.verdict == Verdict.INCONCLUSIVE and budget_stopped:
        r.code = UNDECIDED
        r.reasons.append(
            f"The budget (${r.thresholds['budget']:.2f}) ran out before the result was decided."
        )
        return r
    if r.verdict == Verdict.HURTS:
        r.reasons.append(
            f"It hurts: {pts:+.1f} pts (95% interval {r.ci_low * 100:+.1f} to {r.ci_high * 100:+.1f})."
        )
    elif r.verdict != Verdict.HELPS and pts < min_delta:
        r.reasons.append(f"Difference {pts:+.1f} pts is under the minimum {min_delta:+.1f} pts.")
    _adherence_reason(r, min_adherence)
    r.code = FAIL if r.reasons else PASS
    return r


def _adherence_reason(r: GateResult, min_adherence: float) -> None:
    ad = r.adherence
    if ad is None:
        r.warnings.append("Adherence not checked: no session logs to read for this treatment.")
    elif ad["read"] == 0:
        r.warnings.append("Adherence not checked: no session log could be read.")
    elif ad["followed"] / ad["read"] < min_adherence:
        r.reasons.append(
            f"Only {ad['followed']} of {ad['read']} runs followed the workflow "
            f"({ad['followed'] / ad['read']:.0%}, minimum {min_adherence:.0%})."
        )


def _decide_metric(r: GateResult, min_adherence: float, budget_stopped: bool) -> GateResult:
    v = r.metric_verdict or {}
    noun = rig_mod.M["nouns"][r.metric]
    if v.get("id") == "cant":
        r.code = UNDECIDED
        if budget_stopped:
            r.reasons.append(
                f"The budget (${r.thresholds['budget']:.2f}) ran out before the result on "
                f"{noun} was decided."
            )
        r.reasons.append(f"On {noun}: {v.get('word')}. {v.get('reason') or ''}".rstrip())
        return r
    if v.get("id") != "helps":
        r.reasons.append(f"On {noun}: {v.get('word')}. {v.get('reason') or ''}".rstrip())
    _adherence_reason(r, min_adherence)
    r.code = FAIL if r.reasons else PASS
    return r


def _scenario_rows(trials) -> list[ScenarioRow]:
    rows: dict[str, ScenarioRow] = {}
    for t in trials:
        if t.outcome not in ("pass", "fail"):
            continue
        row = rows.setdefault(t.scenario_id, ScenarioRow(t.scenario_id, 0, 0, 0, 0))
        if t.arm == "with":
            row.with_total += 1
            row.with_pass += t.outcome == "pass"
        else:
            row.without_total += 1
            row.without_pass += t.outcome == "pass"
    return [rows[k] for k in sorted(rows)]


def _adherence(treatment: Path, trials, model: str, who: str) -> dict | None:
    wf_file = treatment / "workflow.json"
    if not wf_file.is_file():  # a plain skill has no steps to follow
        return None
    import json

    wf = json.loads(wf_file.read_text())
    checked = [
        adherence.check(wf, Path(t.transcript_uri), model, who)
        for t in trials
        if t.arm == "with" and t.transcript_uri and t.outcome in ("pass", "fail")
    ]
    s = adherence.summarize(checked)
    return {"followed": s["followed"], "read": s["read"]}


def run_gate(
    treatment: Path,
    bench_id: str,
    *,
    min_delta: float = 0.0,
    min_adherence: float = 0.85,
    budget: float = 2.0,
    agent_id: str = "claude-code",
    size: str = "pilot",
    model: str = DEFAULT_MODEL,
    home: Path | None = None,
    creds: Credentials | None = None,
    on_event: Callable[[Event], None] | None = None,
    local_model: local_mod.LocalModel | None = None,
    metric: str = "pass_rate",
) -> GateResult:
    """Run the experiment to the end here and decide. Never raises for a broken run: that is
    exit code 2 with the reason in `reasons`. `local_model`: Claude Code on it, as the Lab's
    runs on one (free, no sign-in, a longer time limit)."""
    home = home or HOME
    thresholds = {"min_delta": min_delta, "min_adherence": min_adherence, "budget": budget}
    lm = local_model
    shown = f"{lm.label} (local)" if lm is not None else model
    r = GateResult(UNDECIDED, treatment.name, bench_id, agent_id, shown, thresholds)
    r.metric = metric

    def broke(msg: str) -> GateResult:
        r.code = UNDECIDED
        r.reasons.append(msg)
        return r

    try:
        agent(agent_id)
    except KeyError:
        return broke(f"Unknown agent {agent_id!r}.")
    if size not in ("pilot", "full"):
        return broke(f"--size is pilot or full, not {size!r}.")
    if not (treatment / "SKILL.md").is_file():
        return broke(f"{treatment} has no SKILL.md.")
    if lm is not None and agent_id != "claude-code":
        return broke(f"A local model runs Claude Code only, not {agent(agent_id).label}.")
    if metric not in rig_mod.M["ids"]:
        return broke(f"--metric is one of {', '.join(rig_mod.M['ids'])}, not {metric!r}.")
    if lm is not None and metric == "cost":  # as `rig run`: nothing to compare
        return broke(local_mod.L["repo"]["cost_metric"])
    creds = creds or Credentials()
    if lm is None and not creds.ready(agent_id):
        return broke(
            f"Not signed in to {agent(agent_id).label}: set ANTHROPIC_API_KEY or "
            "CLAUDE_CODE_OAUTH_TOKEN in the environment."
        )
    use_home(home)
    try:
        b = bench_mod.bench(bench_id)
    except KeyError as e:
        return broke(str(e.args[0]))
    if b.judged:
        return broke(
            f"{b.name} grades documents with a judge model, which pg gate does not set up yet. "
            "Pick a bench whose checks are code."
        )
    try:
        root = bench_mod.refresh(b, home / "benches" / b.id)
        env, harbor_model = creds.env_for(agent_id), None
        if lm is not None:  # every model Claude Code asks for is served by the local one
            (harbor_model, env), model = local_mod.agent_env(lm), lm.id
        n = trial_count(b, size)
        if size == "full" and metric != rig_mod.M["default"]:
            # As the app's full run on a saving: enough pairs for the pass-rate guard to decide.
            n = max(n, rig_mod.metric_guard_pairs())
        prep = prepare_experiment(
            root,
            treatment,
            budget,
            n,
            model,
            agent=agent_id,
            env=env,
            extra_meta={"bench_version": bench_mod.version(b), "metric": metric}
            | ({"local_model": lm.id, "local_label": lm.label} if lm is not None else {}),
            ready_tasks=bench_mod.task_dirs(b),
            harbor_model=harbor_model,
            free=lm is not None,
            timeout_factor=local_mod.L["timeout_factor"] if lm is not None else 1.0,
        )
        execute(prep, on_event or (lambda e: None))
    except (ServiceError, NotRunnableError, PreflightError) as e:
        return broke(f"The bench could not run: {e}")
    except AgentAuthError as e:
        return broke(f"{agent(agent_id).label} could not sign in. Check the key. ({e})")
    except Exception as e:  # noqa: BLE001 - a broken sandbox is exit 2, not a traceback
        return broke(f"The run stopped: {type(e).__name__}: {e}")

    trials = prep.store.trials(prep.eid)
    s = summarize(trials)
    h = s.headline
    r.status = prep.store.get_experiment(prep.eid).status
    r.spent_usd = round(prep.store.spent(prep.eid), 4)
    r.scenarios = _scenario_rows(trials)
    who = run_meta(root, prep.eid).get("agent", agent_id)
    if h is not None:
        r.verdict, r.diff, r.ci_low, r.ci_high, r.pairs = (
            s.verdict.value,
            h.diff,
            h.ci_low,
            h.ci_high,
            h.n_pairs,
        )
    if s.broken:
        r.warnings.append(f"{s.broken} trials could not be set up and were left out.")
    if s.errored:
        r.warnings.append(f"{s.errored} trials errored and were left out.")
    r.adherence = _adherence(treatment, trials, prep.model, who)
    kind = "workflow" if (treatment / "workflow.json").is_file() else "skill"
    rig = metric_rig(trials, metric, source_cost(prep.store), kind, lm is not None)
    if rig is not None:
        m = rig.get("metric") or {}
        r.headline, r.guard = m.get("headline"), m.get("guard")
        r.metric_verdict = {k: rig["verdict"].get(k) for k in ("id", "word", "reason")}
    return decide(r, min_delta, min_adherence, r.status == "stopped_budget")


# ---------- reports ----------


def _pts(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:+.1f} pts"


def _numbers(r: GateResult) -> list[tuple[str, str]]:
    out = []
    if r.metric_verdict is not None:  # scored on a saving: it leads, the pass rate guards it
        out += [
            ("Scored on", rig_mod.M["names"][r.metric]),
            (f"Verdict on {rig_mod.M['nouns'][r.metric]}", r.metric_verdict.get("word") or ""),
        ]
        out += [("Saving", r.headline)] if r.headline else []
        out += [("Guard", r.guard)] if r.guard else []
    out.append(
        ("Verdict" if r.metric_verdict is None else "Pass-rate verdict", r.verdict or "none")
    )
    if r.diff is not None:
        out += [
            ("Difference", _pts(r.diff)),
            ("95% interval", f"{_pts(r.ci_low)} to {_pts(r.ci_high)}"),
        ]
    out.append(("Pairs", str(r.pairs)))
    if r.adherence and r.adherence["read"]:
        out.append(("Followed", f"{r.adherence['followed']}/{r.adherence['read']}"))
    out.append(("Spent", f"${r.spent_usd:.2f} of ${r.thresholds['budget']:.2f}"))
    return out


def format_text(r: GateResult) -> str:
    lines = [f"Gate {r.label}: {r.treatment} on {r.bench} ({r.agent}, {r.model})"]
    lines += [f"  {k}: {v}" for k, v in _numbers(r)]
    for x in r.scenarios:
        lines.append(
            f"  {'ok  ' if x.ok else 'FAIL'} {x.id}: with {x.with_pass}/{x.with_total}, "
            f"without {x.without_pass}/{x.without_total}"
        )
    lines += [f"Reason: {x}" for x in r.reasons]
    lines += [f"Warning: {x}" for x in r.warnings]
    return "\n".join(lines) + "\n"


def format_github_md(r: GateResult) -> str:
    icon = {PASS: "✅", FAIL: "❌", UNDECIDED: "⚠️"}[r.code]
    lines = [
        f"## {icon} Rig gate: {r.label}",
        "",
        f"`{r.treatment}` on bench `{r.bench}` ({r.agent}, {r.model})",
        "",
        "| Measure | Result |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v} |" for k, v in _numbers(r)]
    if r.scenarios:
        lines += ["", "| Task | With | Without | |", "|---|---|---|---|"]
        lines += [
            f"| {x.id} | {x.with_pass}/{x.with_total} | {x.without_pass}/{x.without_total} "
            f"| {'ok' if x.ok else 'worse'} |"
            for x in r.scenarios
        ]
    if r.reasons:
        lines += ["", *[f"- **{x}**" for x in r.reasons]]
    if r.warnings:
        lines += ["", *[f"> Warning: {x}" for x in r.warnings]]
    t = r.thresholds
    need = (
        f"the verdict on {rig_mod.M['nouns'][r.metric]} is helps (the pass rate as its guard)"
        if r.metric != rig_mod.M["default"]
        else f"difference at least {t['min_delta']:+.1f} pts (or the verdict is helps)"
    )
    lines += [
        "",
        f"<sub>Thresholds: {need}, adherence at least {t['min_adherence']:.0%}, "
        f"budget ${t['budget']:.2f}.</sub>",
    ]
    return "\n".join(lines) + "\n"


def format_junit(r: GateResult) -> str:
    cases = r.scenarios
    suite = ET.Element(
        "testsuite",
        name=f"proving-ground.{r.bench}",
        tests=str(len(cases) or 1),
        failures=str(sum(not x.ok for x in cases)) if cases else "0",
        errors="1" if r.code == UNDECIDED and not cases else "0",
    )
    if not cases:
        tc = ET.SubElement(suite, "testcase", classname=r.bench, name=r.treatment)
        if r.code == UNDECIDED:
            ET.SubElement(tc, "error", message="; ".join(r.reasons) or "undecided")
    for x in cases:
        tc = ET.SubElement(suite, "testcase", classname=f"{r.bench}.{r.treatment}", name=x.id)
        if not x.ok:
            ET.SubElement(
                tc,
                "failure",
                message=f"with {x.with_pass}/{x.with_total} is below without "
                f"{x.without_pass}/{x.without_total}",
            )
    if cases and r.code != PASS:  # a gate-level failure the per-scenario cases don't show
        props = ET.SubElement(suite, "system-out")
        props.text = "\n".join(r.reasons)
    ET.indent(suite)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(suite, encoding="unicode") + "\n"
    )


def render(r: GateResult, fmt: str) -> str:
    return {"text": format_text, "github-md": format_github_md, "junit": format_junit}[fmt](r)
