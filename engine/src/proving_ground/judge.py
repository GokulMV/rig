"""Grade a produced document against a rubric, blind, with a model that isn't doing the work.

Rules and values: the judge-documents skill. Called on this machine after a trial whose rule
checks passed; the sandbox only copies the document out.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from proving_ground import skills
from proving_ground.generate.client import GenerationError, ModelClient
from proving_ground.generate.prompt import Prompt

J = skills.load("judge-documents").values
TOOL = {
    "name": "emit_grades",
    "description": "Return a score and one sentence of evidence per rubric criterion.",
    "input_schema": {
        "type": "object",
        "required": ["scores"],
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["criterion", "score", "evidence"],
                    "properties": {
                        "criterion": {"type": "string"},
                        "score": {"type": "integer", "minimum": 1, "maximum": 5},
                        "evidence": {"type": "string"},
                    },
                },
            }
        },
    },
}


@dataclass
class Grade:
    passed: bool
    mean: float
    scores: list[dict]
    reason: str

    def dump(self) -> dict:
        return asdict(self)


def steady(model: ModelClient) -> ModelClient:
    """The same model at temperature 0, when the client can set it."""
    return model.with_temperature(0) if hasattr(model, "with_temperature") else model


def grade(
    model: ModelClient,
    task: str,
    rubric: list[str],
    document: str,
    context: str = "",
    model_name: str | None = None,  # another tier than judge-documents' own (try-it's quick look)
) -> Grade:
    model = steady(model)
    text = (
        f"<task>\n{task}\n</task>\n<context>\n{context[: J['max_context_chars']]}\n</context>\n"
        f"<document>\n{document[: J['max_artifact_chars']]}\n</document>\n"
        "<rubric>\n" + "\n".join(f"{n}. {c}" for n, c in enumerate(rubric, 1)) + "\n</rubric>\n"
        "Return the grades with the emit_grades tool, one per criterion, in order."
    )
    call = model.call(
        Prompt(skills.section("judge-documents", "Judge prompt"), [{"type": "text", "text": text}]),
        TOOL,
        model_name or J["model"],
        1500,
    )
    raw = call.input.get("scores") if isinstance(call.input, dict) else None
    if not isinstance(raw, list) or len(raw) != len(rubric):
        raise GenerationError("The judge didn't score every criterion.")
    lo, hi = J["scale"]
    scores = []
    for crit, r in zip(rubric, raw, strict=True):
        s = max(lo, min(hi, int(r.get("score", lo)))) if isinstance(r, dict) else lo
        scores.append(
            {
                "criterion": crit,
                "score": s,
                "evidence": str(r.get("evidence", ""))[:300] if isinstance(r, dict) else "",
            }
        )
    mean = round(sum(x["score"] for x in scores) / len(scores), 2)
    low = [x for x in scores if x["score"] < J["pass_min"]]
    passed = mean >= J["pass_mean"] and not low
    reason = (
        f"mean {mean} ≥ {J['pass_mean']}"
        if passed
        else (
            f"{low[0]['criterion']} scored {low[0]['score']}"
            if low
            else f"mean {mean} < {J['pass_mean']}"
        )
    )
    return Grade(passed, mean, scores, reason)


def read_context(project: Path, paths: list[str]) -> str:
    out = []
    for rel in paths:
        for f in (
            sorted((project / rel).rglob("*")) if (project / rel).is_dir() else [project / rel]
        ):
            if f.is_file():
                out.append(f"--- {f.relative_to(project)} ---\n{f.read_text(errors='replace')}")
    return "\n".join(out)


def calibrate(
    model: ModelClient, task: str, rubric: list[str], good: str, bad: str, context: str = ""
) -> dict:
    """Trustworthy only if good passes the judge's own bar, bad fails it and sits well below
    it, and the two are far enough apart."""
    model = steady(model)
    g, b = grade(model, task, rubric, good, context), grade(model, task, rubric, bad, context)
    gap = round(g.mean - b.mean, 2)
    reason = ""
    if not g.passed:
        reason = f"The good example failed the judge's bar ({g.reason})."
    elif b.passed:
        reason = "The bad example passed the judge's bar."
    elif b.mean >= J["calibration_bad_max"]:
        reason = f"The bad example scored {b.mean}, not below {J['calibration_bad_max']}."
    elif gap < J["calibration_gap"]:
        reason = f"Good beat bad by {gap}, under {J['calibration_gap']}."
    return {
        "good": g.mean,
        "bad": b.mean,
        "gap": gap,
        "trustworthy": not reason,
        "reason": reason,
    }
