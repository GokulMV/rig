"""The rules behind every step Rig takes, one skill per step.

Each skills/<name>/SKILL.md says in prose how the step works, and its frontmatter holds the
exact values the code uses (models, limits, weights, thresholds). The code reads the values
from here, so the written rule and the behaviour can't drift apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).parent
NAMES = (
    "rough-estimate",
    "estimate-effect",
    "map-architecture",
    "generate-scenarios",
    "curate-catalog",
    "judge-experiment",
    "improve-architecture",
    "place-in-architecture",
    "recommend-for-repo",
    "workflow-patterns",
    "starter-workflows",
    "match-skills",
    "judge-documents",
    "business-workflows",
    "local-models",
    "learned-priors",
    "generate-bench",
    "failure-forensics",
    "treatment-kinds",
    "ablation",
    "improve-from-failures",
    "build-spec",
    "architecture-catalog",
    "starter-skills",
    "public-benchmarks",
    "trial-budget",
    "rig-score",
    "evidence-validity",
    "try-it",
    "glossary",
    "goal-rules",
    "bench-difficulty",
    "tutorial",
    "measurability",
    "repo-goals",
)


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    values: dict[str, Any]
    body: str
    path: Path


@cache
def load(name: str) -> Skill:
    path = HERE / name / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path} has no frontmatter")
    head, body = text[4:].split("\n---\n", 1)
    meta = yaml.safe_load(head) or {}
    return Skill(meta["name"], meta["description"], meta.get("values") or {}, body.strip(), path)


def value(name: str, key: str) -> Any:
    return load(name).values[key]


def section(name: str, heading: str) -> str:
    """The text under a `## heading` in a skill, up to the next heading of the same level."""
    body = load(name).body
    m = re.search(rf"^## {re.escape(heading)}\n+(.*?)(?=^## |\Z)", body, re.S | re.M)
    if not m:
        raise KeyError(f"{name} has no section {heading!r}")
    return m.group(1).strip()
