"""Did the agent follow the workflow? Read from the trial's own session logs.

A compiled workflow asks the agent to run each step as a subagent (the Agent/Task tool) on the
step's model, with the step's name as the call's description. Claude Code keeps its sessions as
JSONL under the trial's agent/sessions/ folder; every subagent launch is a tool_use there with its
description and model. Nothing here calls a model.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

SUBAGENT_TOOLS = {"Task", "Agent"}


@dataclass
class Adherence:
    found: bool  # were session logs there to read at all
    steps: int
    steps_run: int = 0
    models_ok: int = 0
    calls: int = 0
    loop_ok: bool = True
    missing: list[str] = field(default_factory=list)
    wrong_model: list[str] = field(default_factory=list)
    opened: bool | None = None  # did it open the workflow skill at all (None: can't tell)

    @property
    def followed(self) -> bool:
        return (
            self.found
            and self.steps_run == self.steps
            and self.models_ok == self.steps
            and self.loop_ok
        )

    def dump(self) -> dict:
        return asdict(self) | {"followed": self.followed}


def _short(model: str) -> str:
    """'claude-opus-5-5' and 'opus' both mean opus."""
    m = model.lower()
    for name in ("haiku", "sonnet", "opus"):
        if name in m:
            return name
    return m


def subagent_calls(trial_dir: Path) -> list[dict] | None:  # Claude Code
    """Every subagent launch in the trial's main session logs, in order; None if there are none to read."""
    root = trial_dir / "agent" / "sessions"
    files = sorted(root.rglob("*.jsonl")) if root.is_dir() else []
    if not files:
        return None
    calls = []
    for f in files:
        if "subagents" in f.parts:  # a subagent's own session: its launch is in the main one
            continue
        for line in f.read_text(errors="replace").splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            msg = ev.get("message") if isinstance(ev, dict) else None
            content = msg.get("content") if isinstance(msg, dict) else None
            for block in content if isinstance(content, list) else []:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("name") == "Skill"
                ):
                    inp = block.get("input") or {}
                    calls.append({"skill": str(inp.get("skill") or inp.get("name") or "")})
                    continue
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and block.get("name") in SUBAGENT_TOOLS
                ):
                    inp = block.get("input") or {}
                    calls.append(
                        {
                            "description": str(inp.get("description", "")),
                            "model": inp.get("model"),
                            "prompt": str(inp.get("prompt", ""))[:400],
                        }
                    )
    return calls


# A heading counts only at the start of a line or of a logged string, never quoted inside
# text (like the "headed `## Step 1: ...`" in SKILL.md itself).
PHASE = re.compile(
    r'(?:^|(?<="))[ \t]*#{1,6}[ \t]*Step[ \t]+\d+[ \t]*[:.\-][ \t]*([^\n"\\`]+)', re.I | re.M
)
# The line a step's agent prints first (the brief tells it to): `echo "PG_STEP:<step id>"`.
MARKER = re.compile(r"PG_STEP:([A-Za-z0-9_-]+)")


def phase_calls(trial_dir: Path, steps: list[dict]) -> list[dict] | None:
    """For agents that do each step themselves (Codex, Gemini CLI): the step markers the agent
    printed, read from every log under the trial's agent/ folder. A marker names its step, so a
    heading the agent wrote into a document does not count. Only when no marker appears at all
    does it fall back to the `## Step N: <name>` headings."""
    root = trial_dir / "agent"
    files = [
        f
        for f in (sorted(root.rglob("*")) if root.is_dir() else [])
        if f.is_file()
        and f.suffix in (".txt", ".json", ".jsonl", ".log")
        and "setup" not in f.parts
    ]
    if not files:
        return None
    # Inside JSON logs the newlines are escaped: put them back before looking for headings.
    texts = [f.read_text(errors="replace").replace("\\n", "\n") for f in files]
    found = [m for t in texts for m in MARKER.findall(t)]
    if found:
        names = {st["id"]: st["name"] for st in steps}
        return [{"description": names[m], "model": None, "prompt": ""} for m in found if m in names]
    seen = []
    for t in texts:
        seen += [
            {"description": m.strip("*` "), "model": None, "prompt": ""} for m in PHASE.findall(t)
        ]
    return seen


def check(
    workflow: dict, trial_dir: Path, session_model: str, agent: str = "claude-code"
) -> Adherence:
    steps = workflow["steps"]
    by_phase = agent in ("codex", "gemini-cli")
    calls = phase_calls(trial_dir, steps) if by_phase else subagent_calls(trial_dir)
    if calls is None:
        return Adherence(False, len(steps))
    skills_opened = [c["skill"] for c in calls if "skill" in c]
    calls = [c for c in calls if "skill" not in c]
    a = Adherence(True, len(steps), calls=len(calls))
    if not by_phase:
        wid = str(workflow.get("id", ""))
        a.opened = any(wid and wid in s_ for s_ in skills_opened)
    per_step: dict[str, int] = {}
    for st in steps:
        name = st["name"].lower()
        mine = [
            c
            for c in calls
            if name in c["description"].lower()
            or re.search(rf"\b{re.escape(name)}\b", c["prompt"].lower())
        ]
        per_step[st["id"]] = len(mine)
        if not mine:
            a.missing.append(st["name"])
            continue
        a.steps_run += 1
        if by_phase or agent != "claude-code":  # one model for the whole session: nothing to check
            a.models_ok += 1
            continue
        # No model on the call means the session's own model.
        used = _short(mine[0]["model"] or session_model)
        if used == _short(st["model"]):
            a.models_ok += 1
        else:
            a.wrong_model.append(f"{st['name']}: {used} instead of {_short(st['model'])}")
    loops = workflow.get("loops") or ([workflow["loop"]] if workflow.get("loop") else [])
    for _frm, to, mx in loops:
        if per_step.get(to, 0) > 1 + mx:
            a.loop_ok = False
    return a


def summarize(results: list[Adherence]) -> dict:
    read = [r for r in results if r.found]
    return {
        "trials": len(results),
        "read": len(read),
        "steps": results[0].steps if results else None,
        "followed": sum(r.followed for r in read),
        "steps_run": round(sum(r.steps_run / r.steps for r in read) / len(read), 2)
        if read
        else None,
        "models_ok": round(sum(r.models_ok / r.steps for r in read) / len(read), 2)
        if read
        else None,
        "loop_broken": sum(not r.loop_ok for r in read),
        "not_opened": sum(r.opened is False for r in read),
        # Didn't get the treatment: not seen opening it and ran none of its steps. (A trial can
        # follow every step without a Skill call in its log, so not opening alone isn't enough.)
        "not_applied": sum(r.opened is not True and r.steps_run == 0 for r in read),
        "missing": sorted({m for r in read for m in r.missing}),
        # Each skipped step and in how many of the `read` trials: "missing" is their union, so
        # it can list more steps than any one trial skipped.
        "skipped": sorted(
            (
                {"step": m, "trials": sum(m in r.missing for r in read)}
                for m in {m for r in read for m in r.missing}
            ),
            key=lambda x: (-x["trials"], x["step"]),
        ),
        "wrong_model": sorted({w for r in read for w in r.wrong_model})[:6],
    }


def skill_opened(trial_dir: Path, name: str) -> bool | None:  # Claude Code
    """Did the agent open the skill: a Skill tool call naming it, or a Read of its SKILL.md?
    None when there are no session logs to read."""
    root = trial_dir / "agent" / "sessions"
    files = sorted(root.rglob("*.jsonl")) if root.is_dir() else []
    if not files:
        return None
    want = f"{name}/SKILL.md"
    for f in files:
        for line in f.read_text(errors="replace").splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            msg = ev.get("message") if isinstance(ev, dict) else None
            content = msg.get("content") if isinstance(msg, dict) else None
            for block in content if isinstance(content, list) else []:
                if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                    continue
                inp = block.get("input") or {}
                if not isinstance(inp, dict):
                    continue
                if block.get("name") == "Skill" and name in str(
                    inp.get("skill") or inp.get("name") or ""
                ):
                    return True
                if block.get("name") == "Read" and str(inp.get("file_path", "")).endswith(want):
                    return True
    return False


def mcp_tool_calls(trial_dir: Path, servers: list[str]) -> dict[str, int] | None:
    """Tool calls named `mcp__<server>__<tool>` per server in the trial's session logs (subagent
    sessions included); None if there are no logs to read."""
    root = trial_dir / "agent" / "sessions"
    files = sorted(root.rglob("*.jsonl")) if root.is_dir() else []
    if not files:
        return None
    counts = dict.fromkeys(servers, 0)
    for f in files:
        for line in f.read_text(errors="replace").splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            msg = ev.get("message") if isinstance(ev, dict) else None
            content = msg.get("content") if isinstance(msg, dict) else None
            for block in content if isinstance(content, list) else []:
                if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                    continue
                name = str(block.get("name", ""))
                for server in servers:
                    if name.startswith(f"mcp__{server}__"):
                        counts[server] += 1
    return counts


def summarize_mcp(per_trial: list[dict[str, int] | None]) -> dict:
    """'Used the MCP server in X of Y trials' over the "with" trials whose logs could be read."""
    read = [c for c in per_trial if c is not None]
    used = sum(1 for c in read if sum(c.values()) > 0)
    return {
        "trials": len(per_trial),
        "read": len(read),
        "used": used,
        "calls": sum(sum(c.values()) for c in read),
        "text": f"used the MCP server in {used} of {len(read)} trials",
    }
