"""The deeper review: the chosen agent reads the repo (read-only) and proposes changes.

Same read-only command as Map with Archify. Proposals are kept only if their targets are blocks
in the architecture (or added by the same proposal) and at least one cited file exists.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from proving_ground import skills
from proving_ground.architecture import Architecture
from proving_ground.architecture.advise import Proposal, _pid
from proving_ground.architecture.mapper import READ_ONLY, MapError, extract_spec

KINDS = {"split", "merge", "add", "reconnect", "move", "remove", "check"}
IMPACTS = {"reliability", "speed", "agent", "clarity"}


def _clean(root: Path, arch: Architecture, raw: dict) -> Proposal | None:
    ids = {c.id for c in arch.components}
    delta = raw.get("delta") if isinstance(raw.get("delta"), dict) else {}
    added = {a.get("id") for a in delta.get("add", []) if isinstance(a, dict)}
    known = ids | added
    targets = [t for t in raw.get("targets", []) if isinstance(t, str)]
    if not targets or any(t not in known for t in targets):
        return None
    evidence = [
        e for e in raw.get("evidence", [])
        if isinstance(e, str) and ".." not in Path(e).parts and (root / e.strip().lstrip("./")).exists()
    ]  # fmt: skip
    if not evidence:
        return None  # nothing in the repo backs it
    for key in ("connect", "disconnect"):
        delta[key] = [
            x
            for x in delta.get(key, [])
            if isinstance(x, list) and len(x) >= 2 and x[0] in known and x[1] in known
        ]
    delta["remove"] = [x for x in delta.get("remove", []) if x in ids]
    impact = {k: str(v)[:240] for k, v in (raw.get("impact") or {}).items() if k in IMPACTS and v}
    title = str(raw.get("title") or "")[:90]
    if not title or not impact:
        return None
    return Proposal(
        id=_pid("review", title, *targets),
        title=title,
        kind=raw.get("kind") if raw.get("kind") in KINDS else "check",
        targets=targets,
        why=str(raw.get("why") or "")[:600],
        what=str(raw.get("what") or "")[:800],
        impact=impact,
        effort=raw.get("effort") if raw.get("effort") in ("S", "M", "L") else "M",
        evidence=evidence[:5],
        delta=delta,
        source="review",
    )


def review(
    root: Path,
    arch: Architecture,
    agent: str,
    env: dict[str, str] | None = None,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    timeout: int = 900,
) -> list[Proposal]:
    if agent not in READ_ONLY:
        raise MapError("The deeper review runs through Claude Code for now.")
    current = {
        "components": [
            {"id": c.id, "type": c.type, "role": c.role, "label": c.label, "sublabel": c.sublabel}
            for c in arch.components
        ],
        "connections": [{"from": x.from_, "to": x.to, "label": x.label} for x in arch.connections],
    }
    prompt = (
        skills.section("improve-architecture", "Review prompt")
        + "\n\nCurrent architecture:\n"
        + json.dumps(current)
    )
    try:
        done = run(
            READ_ONLY[agent](prompt),
            cwd=root,
            env={**os.environ, **(env or {})},
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as e:
        raise MapError(f"The review took longer than {timeout // 60} minutes.") from e
    data = extract_spec(done.stdout)
    raw = data.get("proposals") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        raise MapError("The agent's reply had no proposals in it.")
    return [p for p in (_clean(root, arch, r) for r in raw if isinstance(r, dict)) if p]
