"""Shared baseline: reuse earlier "without" trials instead of paying for them again.

"Without" is the agent and model with nothing added, so it doesn't depend on what is being
tested. On a bench, its trials are reused when the bench version, model and agent match. Rules
and values: the judge-experiment skill (shared_baseline).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path

from proving_ground import skills
from proving_ground.files import PG_DIR
from proving_ground.models import Scenario
from proving_ground.store import Store

B = skills.value("judge-experiment", "shared_baseline")


@dataclass(frozen=True)
class Reuse:
    reused: int
    saved_usd: float
    sources: list[int]


def meta(root: Path, eid: int) -> dict:
    try:
        return json.loads((root / PG_DIR / "runs" / str(eid) / "meta.json").read_text())
    except (OSError, ValueError):
        return {}


def env_fingerprint(root: Path, agent: str, model: str, env: dict[str, str] | None = None) -> str:
    """A short hash of what the sandbox and agent are made of, beyond the keys reuse already
    compares: the base image recipe, the agent's install step, the Harbor version and, for a
    local model, where it is served. Claude Code itself is installed unpinned at build time, so
    a changed recipe is the only signal we have that "without" may behave differently."""
    from importlib.metadata import PackageNotFoundError, version

    from proving_ground import agents
    from proving_ground.sandbox import compiler

    try:
        harbor = version("harbor")
    except PackageNotFoundError:
        harbor = ""
    e = env or {}
    parts = [
        compiler.base_dockerfile(root),
        agents.install_snippet(agent),
        harbor,
        e.get("ANTHROPIC_BASE_URL", ""),
        e.get("OPENAI_BASE_URL", ""),
        model if (e.get("ANTHROPIC_BASE_URL") or e.get("OPENAI_BASE_URL")) else "",
    ]
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()[:12]


def reuse_without(
    store: Store,
    root: Path,
    project_id: int,
    eid: int,
    scenarios: list[Scenario],
    repeats: int,
    model: str,
    agent: str,
    version: str,
    fingerprint: str | None = None,
) -> Reuse:
    """Copy matching earlier "without" trials into experiment `eid`, for repeats not done yet."""
    if not B["reuse"] or not fingerprint:
        return Reuse(0, 0.0, [])
    done = store.done_keys(eid)
    wanted = {
        (s.id, r) for s in scenarios for r in range(repeats) if (s.id, "without", r) not in done
    }
    if not wanted:
        return Reuse(0, 0.0, [])
    pool: dict[str, list] = {}
    for e in store.list_experiments(project_id):  # newest first
        if e.id == eid or e.model != model:
            continue
        m = meta(root, e.id)
        if m.get("agent") != agent or m.get("bench_version") != version:
            continue
        if m.get("env_fingerprint") != fingerprint:  # runs without one never match
            continue
        for t in store.trials(e.id):
            if t.arm == "without" and t.outcome in B["outcomes"] and t.reused_from is None:
                pool.setdefault(t.scenario_id, []).append((e.id, t))
    reused, saved, sources = 0, 0.0, set()
    for sid, rep in sorted(wanted):
        if not pool.get(sid):
            continue
        src, t = pool[sid].pop(0)
        store.record_trial(eid, replace(t, repeat=rep, cost_usd=0.0, reused_from=src))
        reused += 1
        saved += t.cost_usd
        sources.add(src)
    return Reuse(reused, round(saved, 4), sorted(sources))


def source_cost(store: Store):
    """What a reused trial cost when it ran: the mean of its source run's "without" trials on
    the same task."""

    def cost(t) -> float:
        src = [
            x.cost_usd
            for x in store.trials(t.reused_from)
            if x.arm == "without" and x.scenario_id == t.scenario_id
        ]
        return sum(src) / len(src) if src else 0.0

    return cost
