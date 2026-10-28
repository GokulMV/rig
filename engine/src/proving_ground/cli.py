"""The `pg` command."""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer

from proving_ground import gate as gate_mod
from proving_ground import local_models as local_mod
from proving_ground import rig_score as rig_mod
from proving_ground import skills
from proving_ground.baseline import meta as run_meta
from proving_ground.baseline import source_cost
from proving_ground.beforeafter import BeforeAfterError
from proving_ground.beforeafter import resolve as resolve_change
from proving_ground.files import (
    PG_DIR,
    FileFormatError,
    ensure_pg_dir,
    load_scenarios,
    save_scenario,
)
from proving_ground.generate import client as gen_client
from proving_ground.generate.apply import PlanConflictError
from proving_ground.generate.client import GenerationError
from proving_ground.generate.prompt import build_prompt
from proving_ground.generate.run import generate as run_generate
from proving_ground.generate.run import plan_tool
from proving_ground.generate.schema import DEFAULT_MIX, InvalidPlanError, parse_mix
from proving_ground.intake import run_intake
from proving_ground.models import ScenarioKind
from proving_ground.report import arm_names, format_event, format_metric, format_summary
from proving_ground.runner.harbor import AgentAuthError
from proving_ground.sandbox.doctor import run_checks
from proving_ground.scheduler import NotRunnableError, PreflightError
from proving_ground.service import ServiceError, execute, prepare_experiment
from proving_ground.stats import summarize
from proving_ground.store import Store
from proving_ground.validity import check_problem

app = typer.Typer(
    no_args_is_help=True,
    help="Rig: swap any part of an agent architecture in or out, rerun, and measure what it changes.",
)
scenarios_app = typer.Typer(no_args_is_help=True, help="List and approve scenarios.")
app.add_typer(scenarios_app, name="scenarios")
local_app = typer.Typer(
    no_args_is_help=True, help="Models served on this machine: free runs, no sign-in."
)
app.add_typer(local_app, name="local")

ROOT = typer.Option(Path("."), "--root", help="Project root.")
LOCAL_MODEL = typer.Option(
    None,
    "--local-model",
    help="Run Claude Code on this local model (its id in `rig local list`): free, no API key.",
)
METRICS = ", ".join(rig_mod.M["ids"])


def _fail(msg: str) -> None:
    typer.echo(msg)
    raise typer.Exit(1)


def _locals() -> local_mod.Registry:
    """The local models added here or in the app (<home>/local-models.json)."""
    return local_mod.Registry(gate_mod.HOME / "local-models.json")


def _local(mid: str, code: int = 1) -> local_mod.LocalModel:
    """An added local model by its id ("local:" may be left out), if Claude Code can run on it.
    Exits with `code` when not (`rig gate`'s is 2: broken, not failed)."""
    reg = _locals()
    m = reg.get(mid) or reg.get(f"local:{mid}")
    why = None
    if m is None:
        why = (
            f"No local model {mid!r}. `rig local list` shows the ones added; add one with "
            "`rig local add <server> <model>`, or in the app under Local models."
        )
    elif not m.anthropic:
        why = (
            f"{m.label} can run Claude Code only when its server speaks Anthropic's Messages API "
            "(llama.cpp and Ollama do)."
        )
    if why is not None:
        typer.echo(why, err=code != 1)
        raise typer.Exit(code)
    assert m is not None
    return m


@local_app.command("list")
def local_list() -> None:
    """Show the local models added, with the id --local-model takes."""
    ms = _locals().models()
    if not ms:
        typer.echo("No local models yet. Add one with `rig local add <server> <model>`.")
        return
    for m in ms:
        runs = "can run Claude Code" if m.anthropic else "can't run Claude Code"
        typer.echo(f"{m.id}  {m.label}  {m.base}  {runs}")


@local_app.command("add")
def local_add(
    base: str = typer.Argument(..., help="The server, e.g. http://127.0.0.1:11434."),
    model: str = typer.Argument(..., help="The model's id as the server lists it."),
    kind: str = typer.Option("openai", "--kind", help="ollama, llamacpp, lmstudio, vllm, jan."),
    label: str | None = typer.Option(None, "--label", help="The name it is shown by."),
) -> None:
    """Add a model served on this machine or your network (a public host is refused)."""
    try:
        m = local_mod.make(base, model, kind, label)
    except ValueError as e:
        _fail(str(e))
    m = local_mod.LocalModel(
        m.id, m.label, m.base, m.model, m.kind, local_mod.speaks_anthropic(m.base)
    )
    _locals().add(m)
    runs = "can run Claude Code" if m.anthropic else "can't run Claude Code (no /v1/messages)"
    typer.echo(f"Added {m.id}  {m.label}: {runs}.")


@local_app.command("remove")
def local_remove(
    mid: str = typer.Argument(..., help="Its id, as `rig local list` shows it."),
) -> None:
    """Remove an added local model."""
    reg = _locals()
    m = reg.get(mid) or reg.get(f"local:{mid}")
    if m is None:
        _fail(f"No local model {mid!r}.")
    reg.remove(m.id)
    typer.echo(f"Removed {m.id}.")


@app.command()
def init(root: Path = typer.Argument(Path("."))) -> None:
    """Create .proving-ground/ with scenario and workflow folders."""
    pg = ensure_pg_dir(root)
    for sub in ("scenarios", "workflows"):
        (pg / sub).mkdir(parents=True, exist_ok=True)
    Store.for_project(root)
    typer.echo(f"Initialized {pg}")


@app.command()
def intake(
    root: Path = typer.Argument(Path(".")),
    file: list[Path] = typer.Option(
        [], "-f", "--file", help="Extra file: graph.json, PDF, Markdown, image."
    ),
) -> None:
    """Read the repo and extra files into project sources."""
    res = run_intake(Store.for_project(root), root, file)
    s = res.scan
    typer.echo(f"Files: {s.file_count}{' (truncated)' if s.truncated else ''}")
    typer.echo("Languages: " + (", ".join(f"{k} {v}" for k, v in s.languages.items()) or "none"))
    typer.echo("Stack: " + (", ".join(s.stack) or "none detected"))
    typer.echo("Agent setup: " + (", ".join(s.agent_setup) or "none"))
    if s.skills:
        typer.echo("Skills in repo: " + ", ".join(k.name for k in s.skills))
    if res.graph:
        typer.echo(f"Graph: {res.graph.nodes} nodes, {res.graph.communities} communities")
    typer.echo("Sources: " + ", ".join(k for k, _ in res.sources))
    if res.skipped:
        typer.echo("Skipped (unsupported type): " + ", ".join(res.skipped))


@scenarios_app.command("list")
def scenarios_list(root: Path = ROOT) -> None:
    """Show every scenario with its kind and review status."""
    try:
        items = load_scenarios(root)
    except FileFormatError as e:
        _fail(str(e))
    if not items:
        typer.echo("No scenarios yet.")
        return
    for s in items:
        ready = "ready" if s.runnable else ("needs check" if not s.check else "needs approval")
        typer.echo(f"{s.id}  {s.kind.value}  {s.check_status}  {ready}")


@scenarios_app.command("approve")
def scenarios_approve(scenario_id: str, root: Path = ROOT) -> None:
    """Mark a scenario's check as reviewed so it can run."""
    try:
        items = {s.id: s for s in load_scenarios(root)}
    except FileFormatError as e:
        _fail(str(e))
    s = items.get(scenario_id)
    if s is None:
        _fail(f"No scenario with id '{scenario_id}'.")
    if not s.check:
        _fail(f"Scenario '{scenario_id}' has no check. Add one before approving.")
    if why := check_problem(s.check):
        _fail(f"Scenario '{scenario_id}' can't be approved: {why}")
    save_scenario(root, s.model_copy(update={"check_status": "approved"}))
    typer.echo(f"Approved {scenario_id}")


@app.command()
def report(experiment_id: int, root: Path = ROOT) -> None:
    """Print the result of an experiment."""
    store = Store.for_project(root)
    try:
        e = store.get_experiment(experiment_id)
    except KeyError as err:
        _fail(str(err.args[0]))
    meta = run_meta(root, e.id)
    on = f"{meta.get('local_label', e.model)} (local, free)" if meta.get("local_model") else e.model
    typer.echo(
        f"Experiment {e.id}: {e.treatment_name} ({e.treatment_kind}, {e.treatment_hash[:8]}) "
        f"on {on}, status {e.status}"
    )
    arms = arm_names(e.treatment_kind)  # a code change's are After and Before
    trials = store.trials(experiment_id)
    typer.echo(format_summary(summarize(trials), arms))
    metric = meta.get("metric")
    if metric in rig_mod.M["ids"]:
        cost_of = source_cost(store)
        local = bool(meta.get("local_model"))
        if said := format_metric(trials, metric, cost_of, _kind(e.treatment_kind), local):
            typer.echo(said)


@app.command()
def doctor(root: Path = ROOT) -> None:
    """Check that this machine can run sandboxed trials."""
    checks = run_checks(root.resolve() / PG_DIR / "runs")
    for c in checks:
        typer.echo(f"{'ok  ' if c.ok else 'FAIL'}  {c.name}: {c.detail}")
    if not all(c.ok for c in checks):
        raise typer.Exit(1)


@app.command()
def run(
    treatment: Path | None = typer.Option(
        None, "--treatment", "-t", help="Skill, hook, MCP server or CLAUDE.md to test."
    ),
    before: str | None = typer.Option(
        None, "--before", help="A code change: the commit or branch before (default HEAD)."
    ),
    after: str | None = typer.Option(
        None,
        "--after",
        help="A code change: the commit or branch after (left out: your uncommitted changes).",
    ),
    budget: float | None = typer.Option(
        None, "--budget", help="Stop when this many USD are spent (not needed on a local model)."
    ),
    n: int = typer.Option(40, "--n", help="Cases per arm (spread across scenarios)."),
    model: str = typer.Option("claude-sonnet-5-5", "--model", help="Model for Claude Code."),
    local_model: str | None = LOCAL_MODEL,
    metric: str = typer.Option(
        rig_mod.M["default"], "--metric", help=f"What the run is scored on: {METRICS}."
    ),
    kind: list[ScenarioKind] = typer.Option([], "--kind", help="Only scenarios of this kind."),
    scenario: list[str] = typer.Option([], "--scenario", help="Only these scenario ids."),
    resume: int | None = typer.Option(None, "--resume", help="Continue an earlier experiment."),
    auto: bool = typer.Option(
        False,
        "--auto",
        help="Keep going until it's decided: add pairs while the result is unclear, "
        "up to the budget and the pair caps.",
    ),
    root: Path = ROOT,
) -> None:
    """Run every selected scenario with and without the treatment in sandboxes.

    With --before and/or --after: a code change, run on the commit before and on the change.
    With --local-model: Claude Code on a model served on this machine, free and with no API key.
    """
    code = before is not None or after is not None
    if code and treatment is not None:
        _fail("Pick either -t (an agent change) or --before/--after (a code change), not both.")
    if not code and treatment is None:
        _fail("Pick a change to measure: -t <folder>, or --before/--after for a code change.")
    if metric not in rig_mod.M["ids"]:
        _fail(f"--metric is one of {METRICS}, not {metric!r}.")
    if resume is not None:  # it goes on where it ran and on what it is scored on, as the API's
        was = run_meta(root, resume)
        local_model, metric = was.get("local_model"), was.get("metric", rig_mod.M["default"])
    lm = _local(local_model) if local_model else None
    if lm is not None and metric == "cost" and resume is None:
        _fail(local_mod.L["repo"]["cost_metric"])
    if lm is None and budget is None:
        _fail("Set --budget: the run stops when that many USD are spent.")
    change = None
    if code:  # refused before anything is written, as the API does
        try:
            change = resolve_change(root, before or "HEAD", after)
        except BeforeAfterError as e:
            _fail(str(e))
    env, harbor_model = None, None
    if lm is not None:
        # As the app's: every model Claude Code asks for is served by the local one.
        harbor_model, env = local_mod.agent_env(lm)
        model = lm.id
    elif not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        _fail("Set ANTHROPIC_API_KEY first. `pg doctor` checks everything a run needs.")
    try:
        p = prepare_experiment(
            root,
            treatment,
            budget if budget is not None else 1.0,  # a local run costs nothing either way
            n,
            model,
            kind,
            scenario,
            resume,
            env=env,
            extra_meta={"metric": metric}
            | ({"local_model": lm.id, "local_label": lm.label} if lm is not None else {}),
            harbor_model=harbor_model,
            free=lm is not None,
            timeout_factor=local_mod.L["timeout_factor"] if lm is not None else 1.0,
            # A small local model never opens a skill it is only offered: told to, as in the app.
            nudge=True
            if lm is not None and treatment is not None and (treatment / "SKILL.md").is_file()
            else None,
            change=change,
        )
    except ServiceError as e:
        _fail(str(e))
    if auto:  # the app's stop rule (judge-experiment: auto_extend), on the run's metric
        p.auto = skills.value("judge-experiment", "auto_extend")
    if p.dirty:
        typer.echo(f"Note: uncommitted changes are not included. Running commit {p.commit}.")
    on = f"{lm.label} (local, free)" if lm is not None else p.model
    typer.echo(
        f"Experiment {p.eid}: {p.treatment.name} on {on}, "
        f"{p.repeats} repeats x {len(p.scenarios)} scenarios"
    )
    if metric != rig_mod.M["default"]:
        typer.echo(
            f"Scored on {rig_mod.M['names'][metric].lower()}, with the pass rate as the guard."
        )
    arms = arm_names(p.treatment.kind.value)
    if change is not None:
        said = change.json()
        typer.echo(f"{said['says']} ({said['files_text']})")
    try:
        summary = execute(p, lambda ev: typer.echo(format_event(ev, arms)))
    except (NotRunnableError, PreflightError) as err:
        _fail(str(err))
    except AgentAuthError as err:
        _fail(
            f"Claude Code could not sign in, so the run stopped. Check ANTHROPIC_API_KEY. ({err})"
        )
    typer.echo(format_summary(summary, arms))
    trials = p.store.trials(p.eid)
    said = format_metric(
        trials, metric, source_cost(p.store), _kind(p.treatment.kind.value), bool(lm)
    )
    if said:
        typer.echo(said)


def _kind(treatment_kind: str) -> str:
    """The Rig score's kind for a repo run's treatment (as the API's repo_rig picks it)."""
    known = ("workflow", "hook", "mcp", "instructions", "before_after")
    return treatment_kind if treatment_kind in known else "skill"


@app.command()
def gate(
    treatment: Path = typer.Option(..., "--treatment", "-t", help="Skill or workflow folder."),
    bench: str = typer.Option(..., "--bench", help="Bench id to measure it on."),
    min_delta: float = typer.Option(0.0, "--min-delta", help="Least difference, in points."),
    min_adherence: float = typer.Option(
        0.85, "--min-adherence", help="Share of runs that must follow a workflow."
    ),
    budget: float = typer.Option(2.0, "--budget", help="Stop when this many USD are spent."),
    agent: str = typer.Option("claude-code", "--agent", help="Agent that runs the tasks."),
    size: str = typer.Option("pilot", "--size", help="pilot (one case per scenario) or full."),
    model: str = typer.Option("claude-sonnet-5-5", "--model", help="Model for Claude Code."),
    fmt: str = typer.Option("text", "--format", help="text, github-md or junit."),
    out: Path | None = typer.Option(None, "--out", help="Write the report here, not stdout."),
    local_model: str | None = LOCAL_MODEL,
    metric: str = typer.Option(
        rig_mod.M["default"],
        "--metric",
        help=f"What the gate decides on: {METRICS} (a saving, with the pass rate as its guard).",
    ),
) -> None:
    """Measure a skill or workflow on a bench and exit 0 pass, 1 fail, 2 undecided (CI gate).

    Sign-in comes from the environment (ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN); none is
    needed with --local-model.
    """
    if fmt not in gate_mod.FORMATS:
        typer.echo(f"--format is one of {', '.join(gate_mod.FORMATS)}.", err=True)
        raise typer.Exit(2)
    lm = _local(local_model, code=2) if local_model else None
    res = gate_mod.run_gate(
        treatment,
        bench,
        min_delta=min_delta,
        min_adherence=min_adherence,
        budget=budget,
        agent_id=agent,
        size=size,
        model=model,
        on_event=lambda ev: typer.echo(format_event(ev), err=True),
        local_model=lm,
        metric=metric,
    )
    text = gate_mod.render(res, fmt)
    if out is not None:
        out.write_text(text, encoding="utf-8")
        typer.echo(f"Gate {res.label}. Report written to {out}")
    else:
        typer.echo(text, nl=False)
    raise typer.Exit(res.code)


@app.command()
def generate(
    use_case: str | None = typer.Option(
        None, "--use-case", help="What the agent should do well, in plain words."
    ),
    use_case_file: Path | None = typer.Option(
        None, "--use-case-file", help="Read the use case from this file."
    ),
    mix: str = typer.Option(DEFAULT_MIX, "--mix", help="How many scenarios of each kind."),
    model: str = typer.Option("claude-opus-5-5", "--model", help="Model that writes scenarios."),
    max_tokens: int = typer.Option(32_000, "--max-tokens", help="Output token limit."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be sent, call nothing."),
    root: Path = ROOT,
) -> None:
    """Write a workflow and scenarios for this project with Claude. Checks start unreviewed."""
    try:
        kinds = parse_mix(mix)
        existing = {s.id for s in load_scenarios(root)}
    except (ValueError, FileFormatError) as e:
        _fail(str(e))
    root = root.resolve()
    store = Store.for_project(root)
    pid = store.ensure_project(str(root))
    text = use_case_file.read_text(encoding="utf-8") if use_case_file else use_case
    if text:
        store.add_source(pid, "usecase", "use-case", text)
    sources = store.list_sources(pid)
    if not sources:
        _fail("Nothing to work from. Run `pg intake` or pass --use-case.")
    if dry_run:
        p = build_prompt(sources, kinds, existing)
        typer.echo("Would send: " + ", ".join(p.included))
        if p.dropped:
            typer.echo("Left out (over the size limit): " + ", ".join(p.dropped))
        size = p.chars + len(json.dumps(plan_tool()))
        typer.echo(f"About {size // 4} input tokens of text, to {model}.")
        typer.echo("Asking for: " + ", ".join(f"{n} {k.value}" for k, n in kinds.items()))
        return
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        _fail("Set ANTHROPIC_API_KEY first, or use --dry-run to see what would be sent.")
    try:
        res = run_generate(root, sources, kinds, gen_client.make_client(), model, max_tokens)
    except InvalidPlanError as e:
        _fail(f"{e}\nNothing was written. Run the command again to retry.")
    except (GenerationError, PlanConflictError) as e:
        _fail(str(e))
    w = res.plan.workflow
    typer.echo(f"Workflow {w.id}: {w.name} ({len(w.steps)} steps)")
    for s in res.scenarios:
        typer.echo(f"  {s.id}  {s.kind.value}  {s.title}")
    for t in res.plan.treatments:
        typer.echo(f"Suggested {t.kind.value}: {t.name}. {t.why}")
    typer.echo(f"Tokens: {res.tokens_in} in, {res.tokens_out} out.")
    typer.echo(
        f"Wrote {len(res.written)} files under {PG_DIR}/. Read each check, then run "
        "`pg scenarios approve <id>`."
    )


@app.command()
def serve(
    port: int = typer.Option(7357, "--port", help="Port on 127.0.0.1."),
    root: Path | None = typer.Option(None, "--root", help="Also attach this repo."),
) -> None:
    """Open the web app on http://127.0.0.1:<port>. Attached repos are remembered."""
    import uvicorn

    from proving_ground.api.app import HOME, create_app
    from proving_ground.workspace import Workspace

    ws = Workspace(HOME / "workspace.json")
    if root is not None:
        ws.add(root)
    url = f"http://127.0.0.1:{port}"
    names = ", ".join(r.name for r in ws.repos()) or "no repos yet"
    typer.echo(f"Rig at {url}  ({names})  Ctrl+C to stop")
    uvicorn.run(create_app(workspace=ws), host="127.0.0.1", port=port, log_level="warning")
