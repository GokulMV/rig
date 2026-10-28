"""Try it endpoints: price a try, start it, follow it, stop it, forget it, and keep an input
as a draft scenario. Rules and values: the try-it skill; the work: proving_ground.tryit."""

from __future__ import annotations

import re
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from proving_ground import gate as gate_mod
from proving_ground import judge as judge_mod
from proving_ground import lab, tryit
from proving_ground import local_models as local_mod
from proving_ground.agents import agent as agent_of
from proving_ground.budget import CostModel, in_trial_option, prior_usd
from proving_ground.files import load_scenarios, save_scenario
from proving_ground.models import Scenario, treatment_from_path
from proving_ground.service import DEFAULT_MODEL

T = tryit.T


class TryTarget(BaseModel):
    workflow: dict | None = None  # a Lab workflow (JSON, as on the canvas)
    skill_path: str | None = None  # or a skill on a repo's canvas (?repo=<id>)
    agent: str = "claude-code"
    model: str | None = None
    grade: bool = False  # check each answer against the goal (support / research only)
    # Claude Code on a model served on this machine, as Measure's "Run on": free, no sign-in.
    local_model: str | None = None


class TryPrice(TryTarget):
    n: int = Field(ge=1, le=T["max_inputs"])
    budget_usd: float = Field(gt=0, le=T["max_budget_usd"])


class TryStart(TryTarget):
    inputs: list[str] = Field(min_length=1, max_length=T["max_inputs"])
    budget_usd: float = Field(gt=0, le=T["max_budget_usd"])
    goal: str = Field(default="", max_length=T["max_goal_chars"])
    accept_no_cap: bool = False  # an agent that can't stop itself mid-try: only if accepted


class TryExample(BaseModel):
    goal: str = Field(default="", max_length=4000)
    discipline: str | None = Field(default=None, max_length=64)


class DraftScenario(BaseModel):
    instruction: str = Field(min_length=1, max_length=T["max_input_chars"])
    title: str = Field(default="", max_length=200)


@dataclass
class Target:
    folder: Path  # the treatment: a compiled workflow or the skill
    root: Path | None  # the repo to snapshot; None: an empty folder (a Lab workflow)
    model: str  # what it runs on, as runs record it
    harbor_model: str | None  # what Harbor is told; None: Claude Code's own default
    workflow: dict | None
    discipline: str | None
    label: str
    seen: dict  # earlier runs' costs, per arm (trial-budget evidence)
    local: local_mod.LocalModel | None = None  # the local model it runs on, if any


def mount(
    app: FastAPI,
    *,
    creds,
    home: Path,
    library: Path,
    busy: Callable[[], object | None],
    resolve_skills: Callable[[lab.Workflow], dict[str, str]],
    current: Callable,
    earlier_with: Callable[[str, str, str, str | None], dict],
    judge_client: Callable[[], object | None],
    local: local_mod.Registry | None = None,
) -> dict[str, tryit.TryJob]:
    """`earlier_with(model, agent, treatment, repo)`: earlier runs' costs for the price;
    `judge_client()`: a model for the optional grading, or None; `local`: the local models a
    try can run on (local_model)."""
    jobs: dict[str, tryit.TryJob] = {}
    lock = threading.Lock()
    paid = tryit.TryCosts(home / "try-costs.json")

    def seen_for(model: str, agent_id: str, treatment: str, repo: str | None) -> dict:
        """Earlier tries of this treatment on this model first, else earlier runs' costs."""
        own = paid.get(model, agent_id, treatment)
        return (
            {"with": own, "without": []} if own else earlier_with(model, agent_id, treatment, repo)
        )

    def target(body: TryTarget, repo: str | None, compile_it: bool) -> Target:
        try:
            a = agent_of(body.agent)
        except KeyError as e:
            raise HTTPException(422, str(e.args[0])) from e
        if (body.workflow is None) == (body.skill_path is None):
            raise HTTPException(422, "Try a workflow or a skill: send exactly one of them.")
        lm = local.get(body.local_model) if body.local_model and local is not None else None
        if body.local_model and lm is None:
            raise HTTPException(404, f"No local model {body.local_model!r}.")
        if lm is not None and (body.agent != "claude-code" or not lm.anthropic):
            raise HTTPException(
                422,
                f"{lm.label} can run Claude Code only when its server speaks Anthropic's Messages "
                "API (llama.cpp and Ollama do). Other agents on local models aren't wired up yet.",
            )
        if body.workflow is not None:
            try:
                wf = lab.load_workflow(body.workflow)
            except (KeyError, TypeError, ValueError) as e:
                raise HTTPException(422, f"Not a workflow: {e}") from e
            name = lab.workflow_name(wf, body.agent)
            folder = library / "workflows" / name
            if compile_it:
                texts = resolve_skills(wf)
                try:
                    folder = lab.compile_workflow(wf, folder, texts, body.agent)
                except ValueError as e:
                    raise HTTPException(422, str(e)) from e
            if lm is not None:  # every model Claude Code asks for is served by the local one
                model, harbor = lm.id, lm.model
            elif body.agent == "claude-code":
                models = [st.model for st in wf.steps if st.kind == "do"] or [
                    st.model for st in wf.steps
                ]
                model = body.model or gate_mod.session_model(models)
                harbor = None
            else:
                harbor = a.default_model or ""
                model = harbor or f"{body.agent}:default"
            return Target(
                folder,
                None,
                model,
                harbor,
                wf.dump(),
                wf.discipline,
                wf.name,
                seen_for(model, body.agent, name, None),
                lm,
            )
        p = current(repo)
        path = Path(str(body.skill_path))
        if not path.exists():
            raise HTTPException(404, f"No skill at {path}.")
        model = body.model or (DEFAULT_MODEL if body.agent == "claude-code" else "")
        harbor = None if body.agent == "claude-code" else (a.default_model or "")
        if body.agent != "claude-code":
            model = harbor or f"{body.agent}:default"
        if lm is not None:
            model, harbor = lm.id, lm.model
        return Target(
            path, p.root, model, harbor, None, None, path.name,
            seen_for(model, body.agent, path.name, p.repo.id), lm,
        )  # fmt: skip

    def harbor_name(t: Target) -> str | None:
        """The model Harbor is told, as prepare_experiment names it; None: the agent's default."""
        if t.harbor_model is not None:
            return t.harbor_model or None
        return t.model if "/" in t.model else f"anthropic/{t.model}"

    def hard_cap(agent: str) -> bool:
        return in_trial_option(agent) is not None

    @app.post("/api/try/price")
    def try_price(body: TryPrice, repo: str | None = Query(default=None)):
        """What a try will cost, before it starts and before any sign-in. No model call."""
        t = target(body, repo, compile_it=False)
        grade = body.grade and tryit.gradable(t.discipline)
        costs = CostModel(prior_usd(t.model), t.seen, free=t.local is not None)
        return tryit.price(costs, body.n, body.budget_usd, grade, hard_cap(body.agent)) | {
            "model": t.model,
            "gradable": tryit.gradable(t.discipline),
            "placeholder": tryit.placeholder(t.discipline),
            "discipline": t.discipline,
            # For saying the price plainly: what runs, and on which model.
            "model_label": f"{t.local.label} (local)"
            if t.local is not None
            else lab.W["models"].get(t.model, {}).get("label", t.model),
            "steps": len(t.workflow["steps"]) if t.workflow else None,
        }

    @app.post("/api/try/example")
    def try_example(body: TryExample):
        """The input box's example, from the goal in use (try-it: goal_examples). No model."""
        return tryit.goal_example(body.goal, body.discipline)

    @app.post("/api/try", status_code=202)
    def try_start(body: TryStart, repo: str | None = Query(default=None)):
        try:
            inputs = tryit.check_inputs(body.inputs, body.budget_usd)
        except tryit.TryError as e:
            raise HTTPException(422, str(e)) from e
        if not body.local_model and not creds.ready(body.agent):  # a local model needs none
            label = agent_of(body.agent).label if body.agent else "the agent"
            raise HTTPException(
                400, f"Sign in to {label} first: click the agent at the top right to sign in."
            )
        capped = hard_cap(body.agent)
        if not capped and not body.accept_no_cap:
            raise HTTPException(
                409,
                f"{agent_of(body.agent).label} can't stop itself at a dollar amount, so this try "
                "has no hard cap: an input can cost more than predicted. Tick that you accept "
                "that, or try it on Claude Code.",
            )
        with lock:
            live = next((j for j in jobs.values() if j.active()), None)
            if live is not None:
                raise HTTPException(409, "A try is still going. Stop it or wait for it.")
            if (b := busy()) is not None:
                raise HTTPException(409, f"Run {b} is still going. Try it when it's done.")
            t = target(body, repo, compile_it=True)
            grade = body.grade and tryit.gradable(t.discipline)
            grader = None
            if grade:
                client = judge_client()
                if client is None:
                    raise HTTPException(
                        400,
                        "Checking answers needs a model: add an Anthropic key or sign in to "
                        "Claude Code, or untick the check.",
                    )
                goal = body.goal.strip() or default_goal(t)

                def grader(task: str, answer: str, client=client, goal=goal) -> tuple[bool, str]:
                    g = judge_mod.grade(client, task, [goal], answer, model_name=T["judge_model"])
                    why = (g.scores[0]["evidence"] if g.scores else "") or g.reason
                    return g.passed, (why.splitlines() or [""])[0]

            treatment = treatment_from_path(t.folder)
            job = tryit.TryJob(inputs, body.budget_usd, body.agent, t.model, t.label, capped, grade)
            work = home / "try" / job.id
            lm = t.local
            try:
                runner, root = tryit.prepare(
                    work,
                    treatment,
                    len(inputs),
                    body.agent,
                    harbor_name(t),
                    local_mod.agent_env(lm)[1] if lm is not None else creds.env_for(body.agent),
                    root=t.root,
                    # As a run on one: a small local model never opens a skill it is only offered.
                    nudge=True if lm is not None and t.workflow is None else None,
                    free=lm is not None,
                    timeout_factor=local_mod.L["timeout_factor"] if lm is not None else 1.0,
                )
            except (ValueError, RuntimeError) as e:
                shutil.rmtree(work, ignore_errors=True)
                raise HTTPException(422, str(e)) from e
            # Only the latest try is kept (in memory): starting one forgets the one before.
            jobs.clear()
            jobs[job.id] = job
        costs = CostModel(prior_usd(t.model), t.seen, free=t.local is not None)
        tasks = {f"try-{i + 1}": work / "tasks" / f"try-{i + 1}" for i in range(len(inputs))}
        threading.Thread(
            target=tryit.run,
            args=(job, runner, treatment, root, costs),
            kwargs={
                "task_dirs": tasks,
                "workflow": t.workflow,
                "grader": grader,
                "clean": lambda: shutil.rmtree(work, ignore_errors=True),
                "on_cost": lambda c: paid.add(t.model, body.agent, t.folder.name, c),
            },
            daemon=True,
        ).start()
        return job.view()

    def default_goal(t: Target) -> str:
        if t.workflow is None:
            return f"The answer does what {t.label} is for."
        does = " ".join(st["does"] for st in t.workflow["steps"])
        return f"The answer follows the goal and any policy of the workflow {t.label}: {does}"[
            : T["max_goal_chars"]
        ]

    def job_of(jid: str) -> tryit.TryJob:
        j = jobs.get(jid)
        if j is None:
            raise HTTPException(404, "No such try: it ended and was forgotten, or never ran.")
        return j

    @app.get("/api/try/{jid}")
    def try_get(jid: str):
        return job_of(jid).view()

    @app.post("/api/try/{jid}/stop")
    def try_stop(jid: str):
        j = job_of(jid)
        if not j.active():
            return {"stopping": False}
        j.stop.set()
        return {"stopping": True}

    @app.delete("/api/try/{jid}")
    def try_forget(jid: str):
        """Drop a finished try (its inputs and answers) from memory."""
        j = job_of(jid)
        if j.active():
            raise HTTPException(409, "Stop the try first.")
        jobs.pop(jid, None)
        return {"forgotten": jid}

    @app.post("/api/scenarios/draft")
    def draft_scenario(body: DraftScenario, p=Depends(current)):
        """Keep a tried input: a scenario with it as the instruction and no check yet."""
        words = re.sub(r"[^a-z0-9]+", "-", (body.title or body.instruction).lower()).strip("-")
        base = ("try-" + "-".join(words.split("-")[:5]))[:50].strip("-") or "try"
        taken = {s.id for s in load_scenarios(p.root)}
        sid, k = base, 2
        while sid in taken:
            sid, k = f"{base}-{k}", k + 1
        s = Scenario(
            id=sid,
            title=body.title or body.instruction.strip().splitlines()[0][:80],
            instruction=body.instruction.strip(),
            origin="user",
        )
        save_scenario(p.root, s)
        return {"id": s.id, "title": s.title, "file": f".proving-ground/scenarios/{s.id}.yaml"}

    return jobs
