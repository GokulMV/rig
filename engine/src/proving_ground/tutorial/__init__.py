"""The tutorial's example space: a tiny repo, the skill it tests, its tasks and one recorded run.

Everything here is read from this folder and nothing else: never the person's workspace, repos,
runs or store (the tutorial skill's isolation rule). Nothing here calls a model or Docker; the
run was recorded once by `record.py` on a local model, and this only reads that record.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from proving_ground import rig_score, skills
from proving_ground.files import load_scenarios

HERE = Path(__file__).parent
PROJECT = HERE / "project"
SKILL = HERE / "skill" / "price-tags-style"
RECORDED = HERE / "recorded.json"
# The files the Describe step shows, in this order.
SHOWN = ("README.md", "pricetags/tags.py", "tests/test_tags.py")
_SKIP = {"__pycache__", ".DS_Store"}

T = skills.load("tutorial").values


def _files(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and not _SKIP.intersection(p.relative_to(root).parts) and p.suffix != ".pyc"
    )


def fingerprint(project: Path = PROJECT, skill: Path = SKILL) -> str:
    """SHA-256 over the example's files (the repo, its tasks and the skill): a recorded run made
    on other files says so (`stale`)."""
    h = hashlib.sha256()
    for name, root in (("project", project), ("skill", skill)):
        for f in _files(root):
            h.update(f"{name}/{f.relative_to(root).as_posix()}".encode() + b"\0")
            h.update(f.read_bytes() + b"\0")
    return h.hexdigest()


def _skill() -> dict[str, Any]:
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    head, body = text[4:].split("\n---\n", 1)
    meta = {
        k.strip(): v.strip().strip('"')
        for k, v in (line.split(":", 1) for line in head.splitlines() if ":" in line)
    }
    return {
        "name": meta["name"],
        "description": meta["description"],
        "path": f".claude/skills/{meta['name']}/SKILL.md",
        "text": text,
        "body": body.strip(),
    }


def example() -> dict[str, Any]:
    """The repo as the Describe step shows it, the skill, and the tasks with their checks."""
    return {
        "name": PROJECT.name if PROJECT.name != "project" else "pricetags",
        "files": [{"path": p, "text": (PROJECT / p).read_text(encoding="utf-8")} for p in SHOWN],
        "skill": _skill(),
        "tasks": [
            {
                "id": s.id,
                "title": s.title,
                "kind": s.kind.value,
                "instruction": s.instruction,
                "check": s.check,
            }
            for s in load_scenarios(PROJECT)
        ],
    }


def recorded() -> dict[str, Any] | None:
    try:
        return json.loads(RECORDED.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _model_label(rec: dict) -> str:
    """"Qwen3.5 9B (Q4_0)" from the weights' file name."""
    stem = rec["model"]["file"].removesuffix(".gguf")
    name, _, quant = stem.rpartition("-")
    name = name.replace("-", " ") if name else stem
    return f"{name} ({quant})" if name and quant else stem


def run_view(rec: dict) -> dict[str, Any]:
    """The recorded run as the pages show it: per task, each arm's outcome; the counts; the
    interval; and the Rig score the app computed for it."""
    tasks = []
    for t in rec["tasks"]:
        row = {"id": t["id"], "title": t["title"]}
        for arm in ("with", "without"):
            trials = t.get(arm) or []
            row[arm] = {
                "passed": sum(x["outcome"] == "pass" for x in trials),
                "trials": len(trials),
                "outcomes": [x["outcome"] for x in trials],
                "seconds": [x["seconds"] for x in trials],
                "details": [x.get("detail") or "" for x in trials],
            }
        tasks.append(row)
    h = rec["summary"]["headline"] or {}
    n = h.get("n_pairs", 0)
    return {
        "recorded": rec["recorded"],
        "model": rec["model"] | {"label": _model_label(rec)},
        "skill": rec["skill"],
        "tasks": tasks,
        "n": n,
        "with": round(h["pass_with"] * n) if h else 0,
        "without": round(h["pass_without"] * n) if h else 0,
        "diff": h.get("diff"),
        "ci_low": h.get("ci_low"),
        "ci_high": h.get("ci_high"),
        "verdict": rec["summary"]["verdict"],
        "ledger": rec["ledger"],
        "rig": rig_score.relabel(rec["rig"]),
        "stale": rec.get("fingerprint") != fingerprint(),
    }


def _moved(tasks: list[dict]) -> dict[str, int]:
    """How many tasks the skill moved each way: fail to pass, pass to fail, or neither."""
    w = [t["with"]["passed"] / max(1, t["with"]["trials"]) for t in tasks]
    wo = [t["without"]["passed"] / max(1, t["without"]["trials"]) for t in tasks]
    helped = sum(a > b for a, b in zip(w, wo, strict=True))
    hurt = sum(a < b for a, b in zip(w, wo, strict=True))
    return {"helped": helped, "hurt": hurt, "same": len(tasks) - helped - hurt}


class _Fill(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _fill(v: Any, f: dict) -> Any:
    if isinstance(v, str):
        return v.format_map(f)
    if isinstance(v, list):
        return [_fill(x, f) for x in v]
    if isinstance(v, dict):
        return {k: _fill(x, f) for k, x in v.items()}
    return v


def _pts(x: float | None) -> str:
    return "?" if x is None else f"{x * 100:+.0f}"


def view() -> dict[str, Any]:
    """Everything the tutorial shows: its words (tutorial skill) with the example's and the run's
    facts filled in, the example, and the run (None until one is recorded)."""
    ex = example()
    rec = recorded()
    run = run_view(rec) if rec else None
    rig = (run or {}).get("rig") or {}
    f = _Fill(
        example=ex["name"],
        skill=ex["skill"]["name"],
        tasks=len(ex["tasks"]),
        n=len(ex["tasks"]) if run is None else run["n"],
    )
    if run:
        f |= {
            "model": run["model"]["label"],
            "server": run["model"]["server"],
            "model_file": run["model"]["file"],
            "timeout_factor": run["model"]["timeout_factor"],
            "date": run["recorded"],
            "with_": run["with"],
            "without": run["without"],
            "diff": _pts(run["diff"]),
            "low": _pts(run["ci_low"]),
            "high": _pts(run["ci_high"]),
            "score": "—" if rig.get("score") is None else rig["score"],
            **_moved(run["tasks"]),
            "label": rig.get("label", ""),
        }
    return {"text": _fill(T, f), "example": ex, "run": run}
