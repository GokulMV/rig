"""Try it: run a workflow or skill once per pasted input and show what came back.

Rules and values: the try-it skill. One sample, not a measurement: there is no check, nothing
passes or fails. Each input runs as a "with" trial would (the same task folder, the treatment
handed over the same way), held to a hard per-try budget (trial-budget). Nothing here calls a
model except the optional grader the caller passes in.
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from proving_ground import adherence, skills
from proving_ground.budget import CostModel, Ledger
from proving_ground.models import Scenario, Treatment
from proving_ground.runner.base import Runner, TrialSpec
from proving_ground.runner.harbor import AgentAuthError, HarborRunner, claude_result_in
from proving_ground.sandbox.compiler import CompileOptions, compile_task
from proving_ground.sandbox.snapshot import snapshot_repo
from proving_ground.sandbox.treatments import is_config

T = skills.load("try-it").values

# Grades one answer: (followed, one-line reason). Raises on failure; the answer stays ungraded.
Grader = Callable[[str, str], tuple[bool, str]]


class TryError(ValueError):
    """A try that cannot start. The message is meant for the person."""


def check_inputs(inputs: list[str], budget: float) -> list[str]:
    """The inputs, stripped; raises TryError when they or the budget are out of bounds."""
    out = [t.strip() for t in inputs]
    if not 1 <= len(out) <= T["max_inputs"]:
        raise TryError(f"Paste between 1 and {T['max_inputs']} inputs.")
    for n, t in enumerate(out, 1):
        if not t:
            raise TryError(f"Input {n} is empty.")
        if len(t) > T["max_input_chars"]:
            raise TryError(f"Input {n} is longer than {T['max_input_chars']:,} characters.")
    if not 0 < budget <= T["max_budget_usd"]:
        raise TryError(f"The budget must be above $0 and at most ${T['max_budget_usd']}.")
    return out


def gradable(discipline: str | None) -> bool:
    return discipline in T["graded_disciplines"]


def placeholder(discipline: str | None) -> str:
    p = T["placeholders"]
    return p.get(discipline or "", p["default"])


def goal_example(goal: str, discipline: str | None) -> dict:
    """The input box's example for this goal (try-it: goal_examples): {"kind", "example"}. The
    kind whose words the goal mentions most; none: the discipline's placeholder. No model."""
    text = (goal or "").lower()
    best, hits = None, 0
    for k in T["goal_examples"]:
        n = sum(1 for w in k["words"] if re.search(rf"(?<!\w){re.escape(w.lower())}(?!\w)", text))
        if n > hits:
            best, hits = k, n
    if best is None:
        return {"kind": discipline or "default", "example": placeholder(discipline)}
    amount = int(T["default_amount"])
    if m := re.search(r"\$\s?(\d[\d,]*)", goal):
        limit = int(m.group(1).replace(",", ""))
        amount = limit + max(1, round(limit * float(T["over_limit"])))
    return {"kind": best["kind"], "example": best["example"].replace("{amount}", f"{amount:,}")}


def price(costs: CostModel, n: int, budget: float, grade: bool, hard_cap: bool) -> dict:
    """Before a try: what one input is predicted to cost (the budget check's own number for a
    "with" trial, margin included), the grading on top, the total, and how many inputs fit."""
    per, source = costs.estimate("with", [])
    judge = float(T["judge_call_usd"]) if grade else 0.0
    each = per + judge
    return {
        "inputs": n,
        "per_input": round(per, 4),
        "judge_per_input": judge,
        "total_usd": round(each * n, 4),
        "cap_usd": budget,
        "hard_cap": hard_cap,
        "source": source,
        "free": costs.free,
        "inputs_in_budget": n if each <= 0 else min(n, int((budget + 1e-9) // each)),
    }


def final_answer(trial_dir: Path, agent: str) -> str | None:
    """The agent's last message: Claude Code's closing `result` event, else the last agent step
    of Harbor's trajectory (agent/trajectory.json). None when neither is there."""
    text: str | None = None
    if agent == "claude-code":
        ev = claude_result_in(trial_dir)
        if ev and isinstance(ev.get("result"), str) and ev["result"].strip():
            text = ev["result"]
    if text is None:
        try:
            traj = json.loads((trial_dir / "agent" / "trajectory.json").read_text())
        except (OSError, ValueError):
            traj = None
        steps = traj.get("steps") if isinstance(traj, dict) else None
        for st in reversed(steps if isinstance(steps, list) else []):
            if not isinstance(st, dict) or st.get("source") != "agent":
                continue
            msg = st.get("message")
            if isinstance(msg, list):
                msg = "\n".join(
                    str(p.get("text", "")) for p in msg if isinstance(p, dict) and p.get("text")
                )
            if isinstance(msg, str) and msg.strip():
                text = msg
                break
    if text is None:
        return None
    text = text.strip()
    cap = T["max_answer_chars"]
    return text if len(text) <= cap else text[:cap] + "\n… (cut here)"


def steps_followed(
    trial_dir: Path, workflow: dict | None, skill: str, session_model: str, agent: str
) -> dict | None:
    """For a workflow: the steps it ran, from its session logs (adherence). For a plain skill:
    whether it opened it. None when there are no logs to tell."""
    if workflow is not None:
        a = adherence.check(workflow, trial_dir, session_model, agent)
        if not a.found:
            return None
        return {"kind": "workflow", "steps": a.steps, "ran": a.steps_run, "missing": a.missing}
    opened = adherence.skill_opened(trial_dir, skill) if agent == "claude-code" else None
    return None if opened is None else {"kind": "skill", "opened": opened}


def _error_detail(trial_dir: Path) -> str:
    try:
        ei = json.loads((trial_dir / "result.json").read_text()).get("exception_info") or {}
    except (OSError, ValueError, AttributeError):
        ei = {}
    if isinstance(ei, dict) and ei.get("exception_type"):
        return f"{ei['exception_type']}: {str(ei.get('exception_message', ''))[:300]}"
    return "The agent stopped with an error before finishing."


@dataclass
class TryResult:
    index: int
    status: str = "waiting"  # waiting running done capped errored broken skipped stopped
    answer: str | None = None
    steps: dict | None = None
    cost_usd: float = 0.0
    duration_s: float = 0.0
    detail: str = ""
    grade: dict | None = None  # {followed, reason, cost_usd} or {error}

    def dump(self) -> dict:
        return asdict(self)


class TryCosts:
    """What earlier tries cost, per (model, agent, treatment): only the amounts, the latest
    `remember_costs` of each, in one small JSON file. Read first when a try is priced."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()

    def _read(self) -> dict[str, list[float]]:
        try:
            got = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        return got if isinstance(got, dict) else {}

    @staticmethod
    def _key(model: str, agent: str, treatment: str) -> str:
        return f"{agent}|{model}|{treatment}"

    def get(self, model: str, agent: str, treatment: str) -> list[float]:
        got = self._read().get(self._key(model, agent, treatment), [])
        return [float(c) for c in got if isinstance(c, (int, float)) and c > 0]

    def add(self, model: str, agent: str, treatment: str, cost: float) -> None:
        if cost <= 0:
            return
        with self.lock:
            data = self._read()
            k = self._key(model, agent, treatment)
            data[k] = ([*data.get(k, []), round(cost, 6)])[-int(T["remember_costs"]) :]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data))


@dataclass
class TryJob:
    inputs: list[str]
    budget: float
    agent: str
    model: str
    label: str
    hard_cap: bool
    grade: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = "running"  # running done stopped stopped_budget error
    detail: str = ""
    spent_usd: float = 0.0
    results: list[TryResult] = field(default_factory=list)
    stop: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        if not self.results:
            self.results = [TryResult(i) for i in range(len(self.inputs))]

    def active(self) -> bool:
        return self.status == "running"

    def view(self) -> dict:
        with self.lock:
            return {
                "id": self.id,
                "status": self.status,
                "detail": self.detail,
                "label": self.label,
                "agent": self.agent,
                "model": self.model,
                "budget_usd": self.budget,
                "hard_cap": self.hard_cap,
                "grade": self.grade,
                "spent_usd": round(self.spent_usd, 4),
                "stopping": self.stop.is_set() and self.status == "running",
                "inputs": list(self.inputs),
                "results": [r.dump() for r in self.results],
            }


def prepare(
    work: Path,
    treatment: Treatment,
    n: int,
    agent: str,
    model: str | None,
    env: dict[str, str] | None,
    root: Path | None = None,
    nudge: bool | None = None,
    free: bool = False,  # a local model: trials cost nothing
    timeout_factor: float = 1.0,  # a local model's longer time limit (local-models)
) -> tuple[HarborRunner, Path]:
    """The runner for a try: a task folder per input, built as a run's "with" arm builds them.
    `root`: the repo to snapshot; None (a Lab workflow) is an empty folder. Returns the runner
    and the project root its tasks were built from. Inputs are written in run() per input."""
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    if root is None:
        root = work / "project"
        root.mkdir()
        (root / "README.md").write_text(T["empty_readme"])
    snap = snapshot_repo(root, work / "snapshot")
    tasks: dict[str, Path] = {}
    for i in range(n):
        s = scenario_for(i, "(the input goes here when its turn comes)")
        tasks[s.id] = compile_task(
            s,
            root,
            snap.path,
            work / "tasks" / s.id,
            CompileOptions(agent_timeout_factor=timeout_factor),
            agent=agent,
            treatment=treatment,
            arm="with",  # a hook / MCP / instructions treatment is written in for "with"
        )
    shutil.rmtree(snap.path, ignore_errors=True)
    runner = HarborRunner(
        tasks,
        work / "trials",
        model=model,
        agent=agent,
        env=env,
        nudge=nudge,
        free=free,
        with_task_dirs=tasks if is_config(treatment) else None,
    )
    return runner, root


def scenario_for(i: int, text: str) -> Scenario:
    return Scenario(
        id=f"try-{i + 1}",
        title=f"Try {i + 1}",
        instruction=f"{text.rstrip()}\n\n{T['answer_note']}",
        check="true",  # no check: a try shows what it does, it doesn't pass or fail
        check_status="approved",
        timeout=T["timeout_s"],
    )


def run(
    job: TryJob,
    runner: Runner,
    treatment: Treatment,
    repo_root: Path,
    costs: CostModel,
    task_dirs: dict[str, Path] | None = None,
    workflow: dict | None = None,
    grader: Grader | None = None,
    clean: Callable[[], None] | None = None,
    on_cost: Callable[[float], None] | None = None,
) -> None:
    """Run each input once, in order, within the budget; fill in job.results as they finish.
    `task_dirs` (from prepare): each input's instruction is written there just before its turn
    and the folder removed after. `clean` runs at the end, however it ends."""
    ledger = Ledger(job.budget)
    caps = bool(getattr(runner, "caps_cost", False)) and not costs.free
    judge_cost = float(T["judge_call_usd"]) if job.grade and grader is not None else 0.0
    seen: list[float] = []
    final = "done"

    def rest(start: int, status: str, detail: str) -> None:
        with job.lock:
            for r in job.results[start:]:
                r.status, r.detail = status, detail

    def fail(detail: str) -> None:
        with job.lock:
            job.detail = detail
            for r in job.results:
                if r.status == "running":
                    r.status, r.detail = "errored", detail
                elif r.status == "waiting":
                    r.status, r.detail = "stopped", "Not run: the try stopped."

    try:
        for i, text in enumerate(job.inputs):
            res = job.results[i]
            if job.stop.is_set():
                rest(i, "stopped", "Stopped before this input ran.")
                final = "stopped"
                break
            est, _src = costs.estimate("with", seen)
            got = ledger.reserve([est + judge_cost])
            if got is None:
                left = max(0.0, ledger.free())
                rest(
                    i,
                    "skipped",
                    f"Not run: it would cost about ${est + judge_cost:.2f} and ${left:.2f} is left.",
                )
                final = "stopped_budget"
                break
            hold = got[0]
            cap = max(0.0, ledger.claim(hold) - judge_cost) if caps else None
            s = scenario_for(i, text)
            if task_dirs is not None:
                (task_dirs[s.id] / "instruction.md").write_text(s.instruction + "\n")
            with job.lock:
                res.status = "running"
            started = time.monotonic()
            try:
                out = runner.run_trial(
                    TrialSpec(0, s, "with", 0, treatment, job.model, 0, repo_root, max_cost_usd=cap)
                )
            except BaseException:
                ledger.release(hold)
                raise
            trial_dir = Path(out.transcript_uri) if out.transcript_uri else None
            answer = final_answer(trial_dir, job.agent) if trial_dir else None
            capped = False
            if trial_dir and job.agent == "claude-code":
                ev = claude_result_in(trial_dir)
                capped = (ev or {}).get("subtype") == "error_max_budget_usd"
            steps = (
                steps_followed(trial_dir, workflow, treatment.name, job.model, job.agent)
                if trial_dir
                else None
            )
            if out.outcome == "broken":
                status, detail = "broken", "The sandbox didn't build, so the agent never ran."
            elif capped:
                status, detail = "capped", f"Cut short at its cap (${cap or 0:.2f})."
            elif out.outcome == "errored":
                status = "errored"
                detail = (
                    _error_detail(trial_dir) if trial_dir else "The agent stopped with an error."
                )
            elif answer is None:
                status, detail = "errored", "The agent finished but left no final message to show."
            else:
                status, detail = "done", ""
            graded: dict | None = None
            spent = out.cost_usd
            if job.grade and grader is not None and answer and status == "done":
                try:
                    ok, why = grader(text, answer)
                    graded = {"followed": ok, "reason": why[:300], "cost_usd": judge_cost}
                except Exception as e:  # noqa: BLE001 - an ungraded answer is still an answer
                    graded = {"error": f"Couldn't check it: {e}"[:300], "cost_usd": judge_cost}
                spent += judge_cost
            ledger.settle(hold, spent)
            if out.cost_usd > 0:
                seen.append(out.cost_usd)
                if on_cost is not None:  # what the next try of it is priced from
                    on_cost(out.cost_usd)
            if trial_dir is not None:
                shutil.rmtree(trial_dir, ignore_errors=True)  # its logs hold the input
            if task_dirs is not None:
                shutil.rmtree(task_dirs[s.id], ignore_errors=True)
            with job.lock:
                res.status, res.detail, res.answer, res.steps = status, detail, answer, steps
                res.cost_usd = round(out.cost_usd, 4)
                res.duration_s = round(out.duration_s or (time.monotonic() - started), 1)
                res.grade = graded
                job.spent_usd = ledger.spent
    except AgentAuthError as e:
        final = "error"
        fail(f"The agent could not sign in. Check the sign-in at the top right. ({e})")
    except Exception as e:  # noqa: BLE001 - say it on the page, not in a dead thread
        final = "error"
        fail(f"The try stopped: {type(e).__name__}: {e}")
    finally:
        if clean is not None:
            clean()
        with job.lock:
            job.spent_usd = ledger.spent
            job.status = final
