"""Instant estimates of a skill's effect, shown before anything is run.

Measured results always win. Otherwise one model call judges the likely change in pass rate
on this repo's scenarios and returns a range with its reason. With no model at all, a rough
guess from the skill's text and the repo stands in, so there is always a number to look at.
Every estimate is a judgement, never a measurement; the app labels it so, and a run replaces it.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from proving_ground import skills
from proving_ground.generate.client import GenerationError, ModelClient
from proving_ground.generate.prompt import Prompt

MODEL = skills.value("estimate-effect", "model")  # the lowest tier: a quick judgement
TOOL = {
    "name": "emit_estimate",
    "description": "Return the estimated change in pass rate, in percentage points.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["low", "high", "likely", "confidence", "reason"],
        "properties": {
            "low": {"type": "number"},
            "high": {"type": "number"},
            "likely": {"type": "number"},
            "confidence": {"enum": ["low", "medium", "high"]},
            "reason": {"type": "string", "maxLength": 300},
        },
    },
}
SYSTEM = skills.section("estimate-effect", "System prompt")


@dataclass(frozen=True)
class EstimateInput:
    name: str
    skill_text: str
    steps: list[str]
    scenarios: list[str]
    repo_summary: str
    measured: dict | None = None  # {"diff", "ci_low", "ci_high", "n_pairs", "experiment_id"}


def _pts(x: float) -> int:
    return round(x * 100)


def _clamp(v: Any) -> int:
    try:
        return max(-100, min(100, round(float(v))))
    except (TypeError, ValueError):
        return 0


class Estimator:
    def __init__(self, model: ModelClient | None, cache: Path):
        self._model = model
        self._cache = cache

    def _key(self, i: EstimateInput) -> str:
        data = asdict(i) | {"measured": None}
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    def _read(self) -> dict:
        try:
            return json.loads(self._cache.read_text())
        except (OSError, ValueError):
            return {}

    def estimate(self, i: EstimateInput, quick: bool = False) -> dict:
        if i.measured and i.measured.get("diff") is not None:
            m = i.measured
            return {
                "basis": "measured",
                "low": _pts(m["ci_low"]),
                "high": _pts(m["ci_high"]),
                "likely": _pts(m["diff"]),
                "confidence": "measured",
                "reason": f"Measured in experiment #{m['experiment_id']} ({m['n_pairs']} pairs).",
            }
        if self._model is None or quick:
            return rough(i)
        key = self._key(i)
        cached = self._read().get(key)
        if cached:
            return cached
        text = (
            f'<skill name="{i.name}">\n{i.skill_text[:8000]}\n</skill>\n'
            f"<repo>\n{i.repo_summary[:6000]}\n</repo>\n"
            f"<scenarios>\n" + "\n".join(f"- {s}" for s in i.scenarios[:40]) + "\n</scenarios>\n"
            f"It would apply to these workflow steps: {', '.join(i.steps) or 'all of them'}.\n"
            "Return the estimate with the emit_estimate tool."
        )
        call = self._model.call(Prompt(SYSTEM, [{"type": "text", "text": text}]), TOOL, MODEL, 600)
        if not isinstance(call.input, dict):
            raise GenerationError("The model did not return an estimate.")
        low, high = sorted((_clamp(call.input.get("low")), _clamp(call.input.get("high"))))
        likely = max(low, min(high, _clamp(call.input.get("likely"))))
        out = {
            "basis": "estimate",
            "low": low,
            "high": high,
            "likely": likely,
            "confidence": call.input.get("confidence")
            if call.input.get("confidence") in ("low", "medium", "high")
            else "low",
            "reason": str(call.input.get("reason") or "")[:300],
        }
        data = self._read()
        data[key] = out
        self._cache.parent.mkdir(parents=True, exist_ok=True)
        self._cache.write_text(json.dumps(data))
        return out


# ---------- The rough guess: no model, instant ----------

WORD = re.compile(r"[a-z][a-z0-9+#.-]{2,}")
TESTY = re.compile(r"\b(tests?|testing|tdd|pytest|jest|vitest|coverage|assert\w*)\b")
REVIEW = re.compile(r"\b(review\w*|verify|verification|check\w*|lint\w*)\b")
R = skills.load("rough-estimate").values
STACK = set(R["stack_terms"])


def rough(i: EstimateInput) -> dict:
    """A deliberately wide guess from how well the skill fits the repo. No model is involved."""
    skill = i.skill_text.lower()
    repo = i.repo_summary.lower() + " " + " ".join(i.scenarios).lower()
    repo_stack = STACK & set(WORD.findall(repo))
    skill_stack = STACK & set(WORD.findall(skill))
    reasons, likely = [], float(R["base_points"])
    shared = sorted(repo_stack & skill_stack)
    if shared:
        likely += min(R["max_shared_terms"], len(shared)) * R["per_shared_stack_term"]
        reasons.append(f"written for {', '.join(shared[:3])}, which this repo uses")
    elif skill_stack and repo_stack:
        likely += R["stack_mismatch"]
        reasons.append(f"written for {', '.join(sorted(skill_stack)[:2])}, not this repo's stack")
    if TESTY.search(skill) and TESTY.search(repo):
        likely += R["tests_bonus"]
        reasons.append("pushes the agent to run tests, and the tasks are checked by tests")
    elif REVIEW.search(skill):
        likely += R["review_bonus"]
        reasons.append("adds a check before finishing")
    if len(i.skill_text) > R["long_skill_chars"]:
        likely += R["long_skill_penalty"]
        reasons.append("long, so it crowds the agent's context")
    likely = max(R["likely_min"], min(R["likely_max"], round(likely)))
    reason = "Rough guess from the skill's text and the repo, no model: " + (
        "; ".join(reasons) if reasons else "nothing in it ties to this repo specifically"
    )
    return {
        "basis": "rough",
        "low": likely - R["half_width"],
        "high": likely + R["half_width"],
        "likely": likely,
        "confidence": R["confidence"],
        "reason": reason[:300] + ".",
    }
