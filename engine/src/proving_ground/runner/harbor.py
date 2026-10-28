"""Run trials through Harbor: Claude Code in a sandbox, graded by the scenario's check."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from proving_ground.budget import in_trial_option
from proving_ground.models import Scenario, TreatmentKind
from proving_ground.runner.base import PreflightResult, TrialSpec
from proving_ground.sandbox.treatments import CONFIG_KINDS
from proving_ground.trial import TIMED_OUT, Outcome, TrialOutcome

AUTH_ERRORS = {"AgentAuthenticationError"}
# The agent ran out of the task's time limit: it didn't finish the task, so the trial fails.
TIMEOUT_ERRORS = {"AgentTimeoutError"}
_AFTER = re.compile(r"after ([0-9.]+) ?s")
RATE_LIMIT_ERRORS = {"ApiRateLimitError"}
BUILD_FAILURE_MARK = "Docker compose command failed"


class AgentAuthError(RuntimeError):
    """The agent could not authenticate. Every remaining trial would fail the same way."""


@dataclass(frozen=True)
class TrialRequest:
    task_dir: Path
    trials_dir: Path
    agent: str
    model: str | None = None
    skills: tuple[str, ...] = ()
    environment: str = "docker"
    env: tuple[tuple[str, str], ...] = ()  # credentials for the agent; never stored
    hosts: tuple[str, ...] = ()  # the agent's model hosts, open only while the agent runs
    prompt_template: Path | None = None  # wraps the task's instruction (a workflow's "with" arm)
    # The agent stops itself at this many USD (trial-budget: in_trial_cap); None: no cap.
    max_cost_usd: float | None = None


Executor = Callable[[TrialRequest], Any]


def harbor_executor(req: TrialRequest) -> Any:
    """Run one Harbor trial and return its TrialResult."""
    from harbor import Trial, TrialConfig
    from harbor.models.trial.config import AgentConfig, EnvironmentConfig, TaskConfig

    async def go() -> Any:
        cfg = TrialConfig(
            task=TaskConfig(path=req.task_dir),
            trials_dir=req.trials_dir,
            agent=AgentConfig(
                name=req.agent,
                model_name=req.model,
                skills=list(req.skills),
                env=dict(req.env),
                extra_allowed_hosts=list(req.hosts),
                kwargs=_agent_kwargs(req),
            ),
            environment=EnvironmentConfig(type=req.environment),
        )
        trial = await Trial.create(cfg)
        return await trial.run()

    return asyncio.run(go())


def _agent_kwargs(req: TrialRequest) -> dict[str, str]:
    out = {"prompt_template_path": str(req.prompt_template)} if req.prompt_template else {}
    option = in_trial_option(req.agent)
    if option and req.max_cost_usd is not None:
        out[option] = f"{req.max_cost_usd:.4f}"
    return out


def _claude_result(trials_dir: Path, result: Any) -> dict | None:
    """Claude Code's closing `result` event (its stream is teed to agent/claude-code.txt)."""
    return claude_result_in(trials_dir / str(getattr(result, "trial_name", "")))


def claude_result_in(trial_dir: Path) -> dict | None:
    """_claude_result for a trial's own folder."""
    path = trial_dir / "agent" / "claude-code.txt"
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if line.startswith("{") and '"type":"result"' in line.replace(" ", ""):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "result":
                return event
    return None


def timed_out_text(message: str, seconds: float = 0.0) -> str:
    """ "timed out after 600 s": the limit from Harbor's message, else how long the trial ran."""
    m = _AFTER.search(message or "")
    limit = float(m.group(1)) if m else seconds
    return f"{TIMED_OUT} after {limit:.0f} s" if limit else TIMED_OUT


def classify(result: Any) -> tuple[Outcome, str]:
    """Map a Harbor TrialResult to pass/fail/errored/broken and a detail. An agent timeout is a
    fail ("timed out after N s"): the agent didn't finish in the task's time limit, whatever the
    check said afterwards. Raises AgentAuthError."""
    ei = result.exception_info
    if ei is not None:
        if ei.exception_type in AUTH_ERRORS:
            raise AgentAuthError(ei.exception_message)
        if ei.exception_type in TIMEOUT_ERRORS:
            return "fail", timed_out_text(ei.exception_message, _seconds(result))
        if BUILD_FAILURE_MARK in ei.exception_message:
            return "broken", ei.exception_message
        return "errored", f"{ei.exception_type}: {ei.exception_message}"
    rewards = result.verifier_result.rewards if result.verifier_result else None
    if not rewards or "reward" not in rewards:
        return "errored", "the check did not record a result"
    return ("pass" if float(rewards["reward"]) >= 1.0 else "fail"), ""


def _seconds(result: Any) -> float:
    if getattr(result, "started_at", None) and getattr(result, "finished_at", None):
        return (result.finished_at - result.started_at).total_seconds()
    return 0.0


def old_trial_detail(trial_dir: Path) -> tuple[Outcome | None, str]:
    """For a trial stored as errored before timeouts were fails: ("fail", "timed out after N
    s") when its Harbor result.json records an agent timeout, else (None, its error or "")."""
    try:
        ei = json.loads((trial_dir / "result.json").read_text()).get("exception_info") or {}
    except (OSError, ValueError, AttributeError):
        return None, ""
    kind, msg = str(ei.get("exception_type") or ""), str(ei.get("exception_message") or "")
    if kind in TIMEOUT_ERRORS:
        return "fail", timed_out_text(msg)
    return None, f"{kind}: {msg}" if kind else ""


def _exit_code(trials_dir: Path, result: Any) -> int | None:
    path = trials_dir / result.trial_name / "verifier" / "exit_code.txt"
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


ITEMS_LINE = re.compile(r"^\s*RIG_ITEMS\s+(\d+)\s*/\s*(\d+)\s*$", re.M)


def items_in(log: str) -> tuple[int, int] | None:
    """Partial credit from a check's output: its last `RIG_ITEMS <right>/<total>` line, or
    None if it printed none (or only a malformed one: total 0, or more right than total)."""
    found = ITEMS_LINE.findall(log)
    if not found:
        return None
    right, total = (int(x) for x in found[-1])
    return (right, total) if 0 <= right <= total and total > 0 else None


def _items(trials_dir: Path, result: Any) -> tuple[int, int] | None:
    path = trials_dir / str(getattr(result, "trial_name", "")) / "verifier" / "check.log"
    try:
        return items_in(path.read_text(errors="replace"))
    except OSError:
        return None


class HarborRunner:
    def __init__(
        self,
        task_dirs: dict[str, Path],
        trials_dir: Path,
        model: str | None,
        executor: Executor | None = None,
        max_attempts: int = 3,
        backoff_s: float = 10.0,
        sleep: Callable[[float], None] = time.sleep,
        agent: str = "claude-code",
        env: dict[str, str] | None = None,
        judge: Callable[[Scenario, Path], tuple[bool, str]] | None = None,
        free: bool = False,
        nudge: bool | None = None,
        with_task_dirs: dict[str, Path] | None = None,
        preflight_with: bool = False,
    ):
        # Hook / MCP / instructions treatments: the "with" arm runs its own task folder
        # (sandbox/treatments.py). None: both arms share `task_dirs`, as skills do.
        self._with_tasks = with_task_dirs
        # Before and after: the arms run different code, so the check is tried on both.
        self._preflight_with = preflight_with and with_task_dirs is not None
        # Grades documents after the rule checks pass (judge-documents); runs here, not in the sandbox.
        self._judge = judge
        self._free = free
        self._nudge = nudge
        self._agent = agent
        self._env = tuple(sorted((env or {}).items()))
        from proving_ground.agents import model_hosts

        self._hosts = tuple(model_hosts(agent, env)) if agent != "nop" else ()
        self._tasks = task_dirs
        self._trials = trials_dir
        self._model = model
        self._executor = executor
        self._max_attempts = max_attempts
        self._backoff = backoff_s
        self._sleep = sleep

    @property
    def free(self) -> bool:
        """A local model: trials cost nothing."""
        return self._free

    @property
    def caps_cost(self) -> bool:
        """The agent stops itself at TrialSpec.max_cost_usd (trial-budget: in_trial_cap)."""
        return not self._free and in_trial_option(self._agent) is not None

    def _cost(self, r: Any) -> float:
        """What one attempt spent: Harbor's number, else Claude Code's own closing event (an
        errored trial can have no agent result and still have spent)."""
        if self._free:
            return 0.0
        ar = r.agent_result
        cost = (ar.cost_usd or 0.0) if ar else 0.0
        if not cost and self._agent == "claude-code":
            total = (_claude_result(self._trials, r) or {}).get("total_cost_usd")
            if isinstance(total, (int, float)):
                cost = float(total)
        return cost

    def _handed(self, path: str | Path) -> Path | None:
        """The "with" arm's prompt names the treatment (judge-experiment: workflow_prompt).
        Default (nudge None): a workflow is handed to the agent, a plain skill is left for it
        to find. True hands any skill over; False hands nothing."""
        folder = Path(path)
        nudge = (folder / "workflow.json").is_file() if self._nudge is None else self._nudge
        if not nudge:
            return None
        from proving_ground import skills

        name = folder.name
        try:
            lines = (folder / "SKILL.md").read_text().splitlines()[1:6]
        except OSError:
            lines = []
        for line in lines:
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
        t = self._trials / "prompts" / f"{name}.j2"
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text(skills.value("judge-experiment", "workflow_prompt").format(skill=name))
        return t

    def _exec(self, req: TrialRequest) -> Any:
        return (self._executor or harbor_executor)(req)

    def preflight(self, scenario: Scenario, repo_root: Path) -> PreflightResult:
        """Build the environment and run the check with no agent (Harbor's `nop` agent). Before
        and after: on both arms' code; a check the after code passes alone tests nothing too."""
        got = self._preflight(self._tasks[scenario.id], scenario)
        if not self._preflight_with or not got.setup_ok or got.check_passed_without_agent:
            return got
        assert self._with_tasks is not None
        after = self._preflight(self._with_tasks[scenario.id], scenario, "with")
        return replace(after, log=f"(the after code) {after.log}" if after.log else "")

    def _preflight(self, task: Path, scenario: Scenario, arm: str = "") -> PreflightResult:
        out = self._trials / ("preflight" if not arm else f"preflight-{arm}")
        req = TrialRequest(task, out, "nop")
        r = self._exec(req)
        ei = r.exception_info
        if ei is not None:
            return PreflightResult(
                scenario.id, False, False, f"{ei.exception_type}: {ei.exception_message}"
            )
        rewards = r.verifier_result.rewards if r.verifier_result else None
        if not rewards or "reward" not in rewards:
            return PreflightResult(scenario.id, False, False, "the check did not record a result")
        return PreflightResult(scenario.id, True, float(rewards["reward"]) >= 1.0)

    def run_trial(self, spec: TrialSpec) -> TrialOutcome:
        kind = spec.treatment.kind
        if kind not in (TreatmentKind.SKILL, TreatmentKind.BEFORE_AFTER, *CONFIG_KINDS):
            raise ValueError(f"{kind.value} treatments are not supported yet")
        is_skill = kind is TreatmentKind.SKILL
        if not is_skill and self._with_tasks is None:
            raise ValueError(f"{kind.value} treatments need a task folder per arm")
        skills = (spec.treatment.path,) if spec.arm == "with" and is_skill else ()
        tasks = self._with_tasks if spec.arm == "with" and not is_skill else self._tasks
        assert tasks is not None
        req = TrialRequest(
            tasks[spec.scenario.id],
            self._trials,
            self._agent,
            self._model,
            skills,
            env=self._env,
            hosts=self._hosts,
            prompt_template=self._handed(spec.treatment.path)
            if spec.arm == "with" and is_skill
            else None,
            max_cost_usd=spec.max_cost_usd if self.caps_cost else None,
        )
        earlier = 0.0  # what rate-limited attempts already spent: it counts, and comes off the cap
        for attempt in range(self._max_attempts):
            r = self._exec(req)
            ei = r.exception_info
            if (
                ei is not None
                and ei.exception_type in RATE_LIMIT_ERRORS
                and attempt < self._max_attempts - 1
            ):
                earlier += self._cost(r)
                if req.max_cost_usd is not None:
                    left = req.max_cost_usd - self._cost(r)
                    if left <= 0:
                        break
                    req = replace(req, max_cost_usd=left)
                self._sleep(self._backoff * 2**attempt)
                continue
            break
        outcome, detail = classify(r)
        if outcome == "pass" and spec.scenario.judge is not None:
            artifact = self._trials / r.trial_name / "verifier" / "artifact.md"
            if self._judge is None or not artifact.is_file():
                outcome = "errored"  # graded work with no judge, or no document to grade
            else:
                try:
                    ok, _why = self._judge(spec.scenario, artifact)
                    outcome = "pass" if ok else "fail"
                except Exception:  # noqa: BLE001 - a judge failure is an errored trial, not a crash
                    outcome = "errored"
        ar = r.agent_result
        if self._agent == "claude-code" and not self._free:
            ev = _claude_result(self._trials, r) or {}
            if ev.get("subtype") == "error_max_budget_usd":
                outcome = "errored"  # cut short at its cap: it measures nothing
                detail = "cut off at its budget cap"
        cost = earlier + self._cost(r)
        items = _items(self._trials, r) if outcome in ("pass", "fail") else None
        return TrialOutcome(
            scenario_id=spec.scenario.id,
            kind=spec.scenario.kind,
            arm=spec.arm,
            repeat=spec.repeat,
            outcome=outcome,
            tokens_in=(ar.n_input_tokens or 0) if ar else 0,
            tokens_out=(ar.n_output_tokens or 0) if ar else 0,
            # A local model costs nothing; the agent's own estimate prices it as a Claude model.
            cost_usd=0.0 if self._free else cost,
            duration_s=_seconds(r),
            exit_code=_exit_code(self._trials, r),
            transcript_uri=str(self._trials / r.trial_name),
            items_right=items[0] if items else None,
            items_total=items[1] if items else None,
            detail=detail or None,
        )
