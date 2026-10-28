"""Is a measured result evidence at all, and is a scenario's check a command?

Rules and values: the evidence-validity skill. Nothing here calls a model.
"""

from __future__ import annotations

import hashlib
import re
import shlex
import shutil
from collections.abc import Iterable

from proving_ground import skills

V = skills.load("evidence-validity").values

VALID, INVALID, UNINFORMATIVE = "valid", "invalid", "uninformative"
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_BARE = re.compile(r"^[A-Za-z][A-Za-z'-]*$")
EXAMPLE = (
    "for example `pytest -q tests/test_refunds.py` or `bash .proving-ground/checks/<id>/check.sh`"
)


def _result(
    status: str, badge: str | None = None, reason: str | None = None, cause: str | None = None
) -> dict:
    """`cause`: broken_check, not_applied, mcp_unused, both_pass, both_fail, each_same; None
    when valid. The Rig score's verdict reads it to say what to do next."""
    return {"status": status, "badge": badge, "reason": reason, "cause": cause}


def judge(
    trials: Iterable,
    adherence: dict | None = None,
    mcp_usage: dict | None = None,
    broken: dict[str, str] | None = None,
) -> dict:
    """{status, badge, reason} for one finished result. `trials` have arm, scenario_id and
    outcome; `adherence` is adherence.summarize's, `mcp_usage` adherence.summarize_mcp's, and
    `broken` maps a scenario id in the run to what is wrong with its check."""
    if broken:
        names = ", ".join(sorted(broken))
        return _result(
            INVALID,
            "Invalid: the check is broken",
            f"Not a command, so every trial fails both ways: {names}.",
            "broken_check",
        )
    ad = adherence or {}
    read = ad.get("read") or 0
    skipped = ad.get("not_applied", ad.get("not_opened")) or 0
    if read and skipped / read > V["max_not_applied_share"]:
        badge = (
            "Invalid: the workflow was never opened"
            if skipped == read
            else f"Invalid: the workflow wasn't opened in {skipped} of {read} trials"
        )
        return _result(
            INVALID,
            badge,
            'The "with" trials mostly ran without it, so the difference isn\'t its.',
            "not_applied",
        )
    mu = mcp_usage or {}
    if mu.get("read") and (mu["read"] - mu.get("used", 0)) / mu["read"] > V["max_unused_mcp_share"]:
        badge = (
            "Invalid: the MCP server was never used"
            if not mu.get("used")
            else f"Invalid: the MCP server went unused in {mu['read'] - mu['used']} of {mu['read']} trials"
        )
        return _result(INVALID, badge, 'The "with" trials mostly never called it.', "mcp_unused")
    # arm -> [passes, finished] per task
    per: dict[str, dict[str, list[int]]] = {}
    for t in trials:
        if t.arm not in ("with", "without") or t.outcome not in ("pass", "fail"):
            continue
        c = per.setdefault(t.scenario_id, {"with": [0, 0], "without": [0, 0]})[t.arm]
        c[0] += t.outcome == "pass"
        c[1] += 1
    rates = [
        (c["with"][0] / c["with"][1], c["without"][0] / c["without"][1])
        for c in per.values()
        if c["with"][1] and c["without"][1]
    ]
    if rates and all(w == wo and w in (0.0, 1.0) for w, wo in rates):
        if all(w == 1.0 for w, _ in rates):
            badge, cause = "Uninformative: both always pass", "both_pass"
        elif all(w == 0.0 for w, _ in rates):
            badge, cause = "Uninformative: both always fail", "both_fail"
        else:
            badge = "Uninformative: each task passes both ways or fails both ways"
            cause = "each_same"
        return _result(
            UNINFORMATIVE, badge, "No task could be won or lost, so it says nothing.", cause
        )
    return _result(VALID)


def check_problem(check: str | None) -> str | None:
    """Why a check isn't a runnable shell command, or None when it reads as one."""
    if not check or not check.strip():
        return "There is no check."
    line = next(
        (ln.strip() for ln in check.splitlines() if ln.strip() and not ln.strip().startswith("#")),
        "",
    )
    if not line:
        return "The check is only comments."
    try:
        words = shlex.split(line, comments=True)
    except ValueError:
        try:  # a quote may open on the first line and close on a later one
            words = shlex.split(check, comments=True)
        except ValueError:
            return f"`{line[:60]}` doesn't split as a shell command (a quote is never closed)."
    rest = list(words)
    while rest and (_ASSIGN.match(rest[0]) or rest[0] in ("!", "time", "(", "{")):
        rest.pop(0)
    if not rest:
        return f"`{line[:60]}` only sets variables; it runs nothing."
    first = rest[0].lstrip("({")
    runners = {str(r) for r in V["check_runners"]}
    if not ("/" in first or first in runners or shutil.which(first)):
        return (
            f"`{line[:60]}` isn't a command: `{first}` is not a program, a path or a known runner. "
            f"A check is a shell command whose exit code says pass or fail, {EXAMPLE}."
        )
    prose = {str(w) for w in V["prose_words"]}
    if all(_BARE.match(w) for w in words) and any(w.lower() in prose for w in words):
        return (
            f"`{line[:60]}` reads as a sentence, not a command. "
            f"A check is a shell command whose exit code says pass or fail, {EXAMPLE}."
        )
    return None


def can_run(s) -> bool:
    """Approved with a check that is a command: the only scenarios a run (or BUILD.md) uses.
    Approved with prose for a check doesn't count as runnable anywhere."""
    return bool(s.runnable) and check_problem(s.check) is None


def counts(scenarios: Iterable) -> dict:
    """How many scenarios, approved, and runnable (can_run), and the approved ones left out
    because their check isn't a command, by name."""
    items = list(scenarios)
    approved = [s for s in items if s.check_status == "approved"]
    return {
        "scenarios": len(items),
        "approved": len(approved),
        "runnable": sum(can_run(s) for s in items),
        "not_command": [s.title or s.id for s in approved if not can_run(s)],
    }


def broken_checks(scenarios: Iterable) -> dict[str, str]:
    """Scenario id -> what is wrong with its check, for scenarios that have a check that isn't a
    command. A scenario with no check at all isn't run, so it isn't listed."""
    out = {}
    for s in scenarios:
        if s.check and (why := check_problem(s.check)):
            out[s.id] = why
    return out


def use_case_tag(text: str | None) -> str:
    """A short stamp for the use case a scenario was written for ("" when there was none)."""
    norm = " ".join((text or "").split()).lower()
    return hashlib.sha1(norm.encode()).hexdigest()[:12] if norm else ""
