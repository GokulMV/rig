"""The skill-matching evaluation: real Lab steps, the real starter-skills index, and the skills a
careful person would attach (fixtures/skill_matching.json). Shared by the floor test and by
anyone re-measuring the matcher by hand:

    uv run python tests/skill_match_eval.py
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from proving_ground import lab

FIXTURES = Path(__file__).parent / "fixtures"


def library() -> list[dict]:
    return json.loads((FIXTURES / "starter_skills_index.json").read_text())["skills"]


def step(ref: str) -> dict:
    """The live step a fixture names: {name, does, kind, words, discipline, origin}."""
    origin, rest = ref.split(":", 1)
    where, sid = rest.split("/", 1)
    if origin == "discipline":
        s = lab.S["disciplines"][where]["steps"][sid]
        return {**s, "words": s.get("words", []), "discipline": where, "origin": origin}
    if origin == "pattern":
        r = next(r for r in lab.W["patterns"][where]["roles"] if r["id"] == sid)
        return {**r, "kind": "do", "words": [], "discipline": "pattern", "origin": origin}
    items = {"business": lab.B, "rag": lab.R}[origin]["workflows"]
    wf = next(w for w in items if w["id"] == where)
    s = next(s for s in wf["steps"] if s["id"] == sid)
    return {**s, "words": [], "discipline": wf["discipline"], "origin": origin}


SPLITS = {
    "tune": ("tune",),  # the only steps the matcher may be tuned on
    "holdout": ("holdout",),
    "fresh": ("fresh",),  # skill_matching_fresh.json: written after the word rules, never tuned on
    "held-out": ("holdout", "fresh"),
    "original": ("tune", "holdout"),  # the first 76 steps, as the floor was set on
    "all": ("tune", "holdout", "fresh"),
}


def split_of(c: dict) -> str:
    return c.get("split") or ("holdout" if c.get("holdout") else "tune")


def cases(holdout: bool | None = None, split: str | None = None) -> list[dict]:
    """The labelled steps. split: a SPLITS name; holdout (older form): True for the holdout
    steps, False for tune; neither: the original 76."""
    if split is None:
        split = "original" if holdout is None else ("holdout" if holdout else "tune")
    out = json.loads((FIXTURES / "skill_matching.json").read_text())["cases"]
    out += json.loads((FIXTURES / "skill_matching_fresh.json").read_text())["cases"]
    out = [c for c in out if split_of(c) in SPLITS[split]]
    return [{**c, "step": c.get("step") or step(c["ref"])} for c in out]


def lab_match(st: dict, lib: list[dict], k: int) -> list[str]:
    """What the Lab attaches to the step now (the word rules unless a matcher is active)."""
    return [s["name"] for s in lab.step_skills(st, lib, k)]


def models_match(models) -> Callable[[dict, list[dict], int], list[str]]:
    """What the Lab attaches once the skill matcher's models are loaded."""
    return lambda st, lib, k: [s["name"] for s in lab.step_skills(st, lib, k, models)]


def evaluate(
    match: Callable[[dict, list[dict], int], list[str]],
    k: int,
    holdout: bool | None = None,
    split: str | None = None,
) -> dict:
    """precision@k: attached skills that are acceptable / all attached (every attachment to a
    step with no acceptable skill is wrong). recall@k: steps with acceptable skills that got at
    least one of them in the top k. false_attach: steps with no acceptable skill that got any."""
    lib = library()
    names = {s["name"] for s in lib}
    attached = right = hit = labelled = none = false = 0
    misses = []
    for c in cases(holdout, split):
        assert set(c["ok"]) <= names, f"{c['ref']}: {set(c['ok']) - names} not in the index"
        got = match(c["step"], lib, k)
        good = [g for g in got if g in c["ok"]]
        attached += len(got)
        right += len(good)
        if c["ok"]:
            labelled += 1
            hit += bool(good)
        else:
            none += 1
            false += bool(got)
        if len(good) != len(got) or (c["ok"] and not good):
            misses.append((c["ref"], got, c["ok"]))
    return {
        "precision": round(right / attached, 3) if attached else 1.0,
        "recall": round(hit / labelled, 3) if labelled else 1.0,
        "false_attach": round(false / none, 3) if none else 0.0,
        "attached": attached,
        "right": right,
        "hits": f"{hit}/{labelled}",
        "false": f"{false}/{none}",
        "misses": misses,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:  # a models folder: measure the models, on the splits named after it
        from proving_ground import skill_models

        ms = skill_models._load(Path(sys.argv[1]))
        for part in sys.argv[2:] or ["tune"]:
            r = evaluate(models_match(ms), 1, split=part)
            print(part, "k=1", {x: v for x, v in r.items() if x != "misses"})
            for m in r["misses"]:
                print("  miss", *m)
        ms.save()
        raise SystemExit
    for part in ("original", "tune", "holdout", "fresh", "held-out"):
        for k in (1, 3):
            r = evaluate(lab_match, k, split=part)
            print(part, f"k={k}", {x: v for x, v in r.items() if x != "misses"})
    for m in evaluate(lab_match, 1, split="tune")["misses"]:
        print("  miss", *m)
