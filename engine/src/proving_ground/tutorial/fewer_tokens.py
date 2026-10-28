"""The tutorial's second track, "Rig your own repo: fewer tokens" (tutorial-tokens skill): a tiny
repo (textkit), a token-saving skill as the change, its tasks, and one recorded run scored on
tokens per solved task, as a repo run with the "Fewer tokens" goal is.

Like the first track it reads only this package's folder (`tokens/`) and the app's own words
(repo-goals, measurability, rig-score), never the person's workspace, repos, runs or store. The
run was recorded once by `record.py --track tokens` on a local model; this only reads it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from proving_ground import rig_score, skills
from proving_ground.files import load_scenarios
from proving_ground.tutorial import _Fill, _fill, _model_label, fingerprint

HERE = Path(__file__).parent / "tokens"
PROJECT = HERE / "project"
SKILL = HERE / "skill" / "lean-context"
RECORDED = HERE / "recorded.json"
# The files the Describe step shows, in this order.
SHOWN = ("README.md", "textkit/case.py", "docs/DESIGN.md")
# The goal template this track walks (repo-goals: templates).
TEMPLATE = "fewer-tokens"
METRIC = "tokens"

T = skills.load("tutorial-tokens").values


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
    """The repo as Describe shows it, the skill, and the tasks with their checks."""
    return {
        "name": "textkit",
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


def _arm(trials: list[dict]) -> dict[str, Any]:
    return {
        "passed": sum(x["outcome"] == "pass" for x in trials),
        "trials": len(trials),
        "outcomes": [x["outcome"] for x in trials],
        "seconds": [x["seconds"] for x in trials],
        "tokens": [x.get("tokens", 0) for x in trials],
        "details": [x.get("detail") or "" for x in trials],
    }


def run_view(rec: dict) -> dict[str, Any]:
    """The recorded run as the pages show it: per task, each arm's passes and tokens; the pass
    counts (the guard); the tokens per solved task and its interval; and the app's Rig score."""
    tasks = [
        {"id": t["id"], "title": t["title"]}
        | {a: _arm(t.get(a) or []) for a in ("with", "without")}
        for t in rec["tasks"]
    ]
    h = rec["summary"]["headline"] or {}
    n = h.get("n_pairs", 0)
    rig = rig_score.relabel(rec["rig"])
    return {
        "recorded": rec["recorded"],
        "model": rec["model"] | {"label": _model_label(rec)},
        "skill": rec["skill"],
        "repeats": rec["repeats"],
        "took_s": rec.get("took_s"),
        "tasks": tasks,
        "n": n,
        "with": round(h["pass_with"] * n) if h else 0,
        "without": round(h["pass_without"] * n) if h else 0,
        "diff": h.get("diff"),
        "ci_low": h.get("ci_low"),
        "ci_high": h.get("ci_high"),
        "verdict": rec["summary"]["verdict"],
        "ledger": rec["ledger"],
        "metric": rig.get("metric"),
        "rig": rig,
        "stale": rec.get("fingerprint") != fingerprint(PROJECT, SKILL),
    }


def _pct(r: float | None) -> str:
    """A ratio with ÷ without as the change it is: 0.8 → "-20%"; None → "no upper end"."""
    return rig_score.MT["unbounded"] if r is None else f"{(r - 1) * 100:+.0f}%"


def _k(v: float | None) -> str:
    return "?" if v is None else f"{v / 1000:.1f}k" if v >= 1000 else f"{v:.0f}"


def _took(s: int | None) -> str:
    if not s:
        return "?"
    h, m = divmod(round(s / 60), 60)
    return f"{h} h {m} min" if h else f"{m} min"


def view() -> dict[str, Any]:
    """Everything the track shows: its words (tutorial-tokens skill) with the app's own labels
    (the goal template, the badges, the metric) and the run's facts filled in, the example, and
    the run (None until one is recorded)."""
    ex = example()
    rec = recorded()
    run = run_view(rec) if rec else None
    goal = next(t for t in skills.value("repo-goals", "templates") if t["id"] == TEMPLATE)
    states = skills.value("measurability", "states")
    M = rig_score.M
    f = _Fill(
        example=ex["name"],
        skill=ex["skill"]["name"],
        tasks=len(ex["tasks"]),
        template=goal["label"],
        template_text=goal["text"],
        metric_name=M["names"][METRIC],
        need=rig_score.metric_guard_pairs(),
        margin=M["margin_pts"],
        **{f"badge_{k}": v["label"] for k, v in states.items()},
    )
    if run:
        m = run["metric"] or {}
        rig = run["rig"] or {}
        f |= {
            "model": run["model"]["label"],
            "server": run["model"]["server"],
            "model_file": run["model"]["file"],
            "timeout_factor": run["model"]["timeout_factor"],
            "date": run["recorded"],
            "repeats": run["repeats"],
            "n": run["n"],
            "with_": run["with"],
            "without": run["without"],
            "tok_with": _k(m.get("with")),
            "tok_without": _k(m.get("without")),
            "change": "?" if m.get("ratio") is None else _pct(m["ratio"]),
            "low": "?" if m.get("low") is None else _pct(m["low"]),
            "high": _pct(m.get("high")) if m.get("low") is not None else "?",
            "guard": m.get("guard") or "",
            "score": "—" if rig.get("score") is None else rig["score"],
            "label": rig.get("label", ""),
            "verdict": (rig.get("verdict") or {}).get("word", ""),
            "reason": (rig.get("verdict") or {}).get("reason", ""),
            "next": (rig.get("verdict") or {}).get("next", ""),
            "took": _took(run["took_s"]),
        }
    text = _fill(T, f)
    # Ship's brief: the change to make only when the run says it helps (tutorial-tokens: ship).
    ship = next(s for s in text["steps"] if s["id"] == "ship")
    helps = bool(run) and ((run["rig"] or {}).get("verdict") or {}).get("id") == "helps"
    ship["brief"] = ship.pop("brief_helps") if helps else ship.pop("brief_not")
    ship.pop("brief_helps", None)
    ship.pop("brief_not", None)
    return {"text": text, "example": ex, "run": run}
