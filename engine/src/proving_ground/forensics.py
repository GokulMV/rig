"""Why did a trial fail, and where did the with and without runs part ways? Read from the trial folder.

A trial leaves agent/sessions/**/*.jsonl (the main session's tool calls), verifier/check.log and
result.json. The rules for the buckets live in the failure-forensics skill. Nothing here calls a model.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from proving_ground import adherence, skills

NAME = "failure-forensics"
MAX_FILES = skills.value(NAME, "max_files_touched")
CAP = skills.value(NAME, "timeline_cap")
FINAL_CHARS = skills.value(NAME, "final_text_chars")
CMD_CHARS = skills.value(NAME, "command_chars")
TEST_WORDS = skills.value(NAME, "test_words")
EDIT_TOOLS = set(skills.value(NAME, "edit_tools"))

FAIL_LINE = re.compile(r"^\s*(FAILED|FAIL:|FAIL |not ok|✖|✗)", re.M)
ASSERTION = re.compile(r"AssertionError")


def _blocks(trial_dir: Path) -> list[dict] | None:
    """Every content block of the main session logs, in order; None if there are no logs."""
    root = trial_dir / "agent" / "sessions"
    files = sorted(root.rglob("*.jsonl")) if root.is_dir() else []
    if not files:
        return None
    out = []
    for f in files:
        if "subagents" in f.parts:
            continue
        for line in f.read_text(errors="replace").splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            msg = ev.get("message") if isinstance(ev, dict) else None
            content = msg.get("content") if isinstance(msg, dict) else None
            if (
                not isinstance(msg, dict)
                or msg.get("role") != "assistant"
                or not isinstance(content, list)
            ):
                continue
            out += [b for b in content if isinstance(b, dict)]
    return out


def _calls(blocks: list[dict]) -> list[tuple[str, dict]]:
    return [
        (str(b.get("name", "")), b.get("input") or {})
        for b in blocks
        if b.get("type") == "tool_use"
    ]


def _final_text(blocks: list[dict]) -> str:
    texts = [str(b.get("text", "")).strip() for b in blocks if b.get("type") == "text"]
    return next((t for t in reversed(texts) if t), "")


def _summary(name: str, inp: dict) -> str:
    if name == "Bash":
        return str(inp.get("command", ""))[:CMD_CHARS]
    if name in EDIT_TOOLS | {"Read"}:
        return str(inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or "")
    if name in adherence.SUBAGENT_TOOLS:
        return str(inp.get("description", ""))
    if name == "Skill":
        return str(inp.get("skill") or inp.get("name") or "")
    return str(inp.get("description") or inp.get("pattern") or "")[:CMD_CHARS]


def timeline(trial_dir: Path) -> list[dict]:
    """The main session's tool calls in order, then the agent's final message."""
    blocks = _blocks(Path(trial_dir))
    if not blocks:
        return []
    out = [{"tool": n, "summary": _summary(n, i)} for n, i in _calls(blocks)]
    final = _final_text(blocks)
    if final:
        out.append({"tool": "Final message", "summary": final[:FINAL_CHARS]})
    return out


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _timed_out(trial_dir: Path) -> bool:
    try:
        info = json.loads(_read(trial_dir / "result.json")).get("exception_info")
    except (ValueError, AttributeError):
        return False
    return "timeout" in json.dumps(info).lower() or "timed out" in json.dumps(info).lower()


def _ran_check_after_last_edit(calls: list[tuple[str, dict]], check_cmd: str) -> bool:
    last = max((i for i, (n, _) in enumerate(calls) if n in EDIT_TOOLS), default=-1)
    words = [w for w in [*TEST_WORDS, check_cmd] if w]
    return any(
        n == "Bash" and any(w in str(inp.get("command", "")) for w in words)
        for n, inp in calls[last + 1 :]
    )


def _failures(check_log: str) -> int:
    """Distinct failing tests in the check's output; failing assertions when it names no tests."""
    named = {m.group(0).strip() for m in re.finditer(FAIL_LINE.pattern + r".*$", check_log, re.M)}
    return len(named) or len(ASSERTION.findall(check_log))


def _files_edited(calls: list[tuple[str, dict]]) -> set[str]:
    return {
        str(i.get("file_path") or i.get("notebook_path") or "") for n, i in calls if n in EDIT_TOOLS
    } - {""}


def _check_cmd(scenario) -> str:
    if isinstance(scenario, dict):
        return str(scenario.get("check") or "")
    return str(getattr(scenario, "check", "") or "")


def classify(trial_dir: Path, outcome: str, scenario, workflow: dict | None = None) -> dict:
    """{bucket, why} for one trial (rules in the failure-forensics skill)."""
    trial_dir = Path(trial_dir)
    if outcome == "pass":
        return {"bucket": "solved", "why": "The check passed."}
    blocks = _blocks(trial_dir)
    if outcome == "fail" and _timed_out(trial_dir):  # an agent timeout is a fail now
        return {"bucket": "timeout", "why": "Ran out of time before a final message."}
    if outcome in ("errored", "broken"):
        if _timed_out(trial_dir) or (blocks is not None and not _final_text(blocks)):
            return {"bucket": "timeout", "why": "Ran out of time before a final message."}
        return {"bucket": "errored", "why": f"The trial {outcome} before it could be judged."}
    if blocks is None:
        return {"bucket": "unknown", "why": "No session logs to read."}
    calls = _calls(blocks)
    if workflow:
        a = adherence.check(workflow, trial_dir, "")
        if a.found and not a.loop_ok:
            return {"bucket": "loop_thrash", "why": "A loop ran past its limit."}
    if not _ran_check_after_last_edit(calls, _check_cmd(scenario)):
        return {"bucket": "premature_stop", "why": "Never ran a test after its last edit."}
    n = _failures(_read(trial_dir / "verifier" / "check.log"))
    if n > 1:
        return {
            "bucket": "regression",
            "why": f"The check shows {n} failures, not just the target.",
        }
    files = _files_edited(calls)
    if len(files) > MAX_FILES:
        return {
            "bucket": "over_engineering",
            "why": f"Edited {len(files)} files (limit {MAX_FILES}).",
        }
    return {"bucket": "wrong_fix", "why": "Ran the check after its edits and it still failed."}


def _diverged_at(a: list[dict], b: list[dict]) -> int | None:
    for i, (x, y) in enumerate(zip(a, b, strict=False)):
        if x["tool"] != y["tool"]:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


def _key(t) -> tuple:
    return (t.scenario_id, t.repeat)


def discordant_count(trials) -> int:
    """How many (scenario, repeat) pairs ended differently with and without. Reads no files."""
    arms: dict[tuple, dict] = {}
    for t in trials:
        arms.setdefault(_key(t), {}).setdefault(t.arm, t.outcome)
    return sum(
        1 for a in arms.values() if "with" in a and "without" in a and a["with"] != a["without"]
    )


def discordant(trials, scenarios: dict | None = None, workflow: dict | None = None) -> list[dict]:
    """Pairs whose with and without outcomes differ, each with both arms' bucket and timeline."""
    scenarios = scenarios or {}
    arms: dict[tuple, dict] = {}
    for t in trials:
        arms.setdefault(_key(t), {}).setdefault(t.arm, t)
    pairs = []
    for (sid, repeat), a in sorted(arms.items()):
        if "with" not in a or "without" not in a or a["with"].outcome == a["without"].outcome:
            continue
        side, lines = {}, {}
        for arm, t in a.items():
            d = Path(t.transcript_uri) if t.transcript_uri else Path("/nonexistent")
            wf = workflow if arm == "with" else None
            side[arm] = {"outcome": t.outcome, **classify(d, t.outcome, scenarios.get(sid), wf)}
            lines[arm] = timeline(d)
        pairs.append(
            {
                "scenario_id": sid,
                "repeat": repeat,
                "with": side["with"],
                "without": side["without"],
                "diverged_at": _diverged_at(lines["with"], lines["without"]),
                "timeline_with": lines["with"][:CAP],
                "timeline_without": lines["without"][:CAP],
            }
        )
    return pairs
