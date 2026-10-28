"""The Rig score explainer: the rig-score skill's parts, weights, gates and bands in plain words,
and a worked example scored by the real formula. Read-only; nothing here calls a model."""

from __future__ import annotations

import copy
from typing import Any

from fastapi import FastAPI

from proving_ground import rig_score as rig_mod
from proving_ground import skills, stats

R = rig_mod.R
X = R["explain"]


def _pct(x: float) -> str:
    return f"{x * 100:.0f}"


def explain() -> dict[str, Any]:
    """Everything the explainer page shows, every number filled in from the skill's values."""
    P, G = R["parts"], R["gates"]
    fill = {
        "lift": {"target_pts": P["lift"]["target_pts"]},
        "cost": {"full": P["cost"]["full"], "zero": P["cost"]["zero"]},
        "followed": {"steps_pct": _pct(P["followed"]["steps_share"])},
        "holds_up": {k: v for k, v in P["holds_up"]["scores"].items()},
        "reliable": {"untrusted_pct": _pct(P["reliable"]["untrusted_judge"])},
    }
    parts = [
        {
            "id": pid,
            "name": P[pid]["name"],
            "weight": P[pid]["weight"],
            "measures": X["parts"][pid]["measures"],
            "scale": X["parts"][pid]["scale"].format(**fill[pid]),
            "needs_lift": pid in R["credit_needs_lift"],
        }
        for pid in rig_mod.ORDER
    ]
    caps = {
        "hurts": G["hurts_cap"],
        "not_shown": G["not_shown_cap"],
        "provisional": G["provisional_cap"],
        "ceiling_worse": G["ceiling_worse_cap"],
    }
    gates = [
        {"id": gid, "cap": cap, "text": X["gates"][gid].format(cap=cap, min_pairs=G["min_pairs"])}
        for gid, cap in caps.items()
    ]
    by_id = {b["id"]: b for b in R["bands"]}
    works, works_but = by_id["works"]["min"], by_id["works_but"]["min"]
    band_fill = {
        "works": {"min": works},
        "works_but": {"min": works_but, "top": works - 1},
        "not_proven": {},
        "helps_but": {"below": works_but},
        "doesnt": {"doesnt_below_pts": R["doesnt_below_pts"]},
    }
    bands = [
        {
            "id": b["id"],
            "tone": b["tone"],
            # "{noun}", "{drag}", "{settle}" are filled per result; here they read as "…".
            "label": b["label"].format(noun="…", drag="…", settle="…"),
            "min": b.get("min"),
            "when": X["bands"][b["id"]].format(**band_fill[b["id"]]),
        }
        for b in R["bands"]
    ]
    names = " and ".join(P[pid]["name"] for pid in R["credit_needs_lift"])
    evidence = copy.deepcopy(X["example"]["evidence"])
    return {
        "intro": X["intro"],
        "parts": parts,
        "missing": X["missing"],
        "no_credit": X["no_credit"].format(names=names),
        "gates": gates,
        "min_pairs": G["min_pairs"],
        "bands": bands,
        "verdict": [
            {"id": k, "word": w, "tone": R["verdict"]["tones"][k]}
            for k, w in R["verdict"]["words"].items()
        ],
        "metric": metric_explained(),
        "example": {
            "title": X["example"]["title"],
            "note": X["example"]["note"].format(weight=_pct(P["holds_up"]["weight"])),
            "evidence": evidence,
            # The real formula, on the example's evidence: the page shows this, never a sum of its own.
            "result": rig_mod.rig_score(copy.deepcopy(evidence)),
        },
    }


def metric_explained() -> dict[str, Any]:
    """What a run can be scored on (rig-score: Metric): the rule in words, and one line per
    metric for the choice on Measure."""
    M, P, G = R["metric"], R["parts"], R["gates"]
    return {
        "text": X["metric"].format(
            target_pct=_pct(M["target_cut"]),
            margin=M["margin_pts"],
            cap=G["not_shown_cap"],
            cost_pct=_pct(P["cost"]["weight"]),
        ),
        "default": M["default"],
        "margin_pts": M["margin_pts"],
        "guard_note": M["guard_note"].format(margin=M["margin_pts"]),
        "options": [
            {"id": m, "name": M["names"][m], "describe": M["describe"][m]} for m in M["ids"]
        ],
        "keep_going": keep_going(),
    }


def keep_going() -> dict[str, str]:
    """The Lab's "Keep going until it's decided", per metric: what it waits for before it stops
    adding pairs (judge-experiment: auto_extend)."""
    A = skills.value("judge-experiment", "auto_extend")
    M, t = R["metric"], A["text"]
    level = f"{stats.level_of(A['stop_z']) * 100:.0f}"
    return {
        m: t["keep_going"].format(level=level)
        if m == M["default"]
        else t["keep_going_metric"].format(
            level=level,
            max_pairs=A["metric"]["max_pairs"],
            small=f"{M['doesnt_below_cut'] * 100:.0f}",
            margin=M["margin_pts"],
            name=M["names"][m].lower(),
        )
        for m in M["ids"]
    }


def mount(app: FastAPI) -> None:
    @app.get("/api/rig-score")
    def rig_score_explained():
        """The Rig score's definition (rig-score skill) and one worked example, for its explainer page."""
        return explain()
