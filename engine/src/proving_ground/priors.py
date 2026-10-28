"""Learned priors: measured runs move the Lab's starting guesses, and what a solved task cost.

Rules and values: the learned-priors skill. Nothing here calls a model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from proving_ground import skills

P = skills.load("learned-priors").values


@dataclass(frozen=True)
class Learned:
    prior: float  # points, the guess moved towards the measurements (the guess when "shape")
    guess: float  # the starting guess from the workflow's shape
    runs: int  # valid measured runs it learned from
    pairs: int  # their pairs
    # "learned": enough valid pairs moved the guess; "shape": too few, so it stays the guess.
    basis: str = "learned"
    need_pairs: int = 0  # valid pairs needed before it is "learned"
    ignored: int = 0  # similar runs skipped because they aren't evidence (evidence-validity)

    def dump(self) -> dict:
        return asdict(self)


def similarity(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def model_tier(model_id: str) -> str:
    """local (served on this machine), cloud_fast (haiku, mini, flash) or cloud_frontier."""
    m = (model_id or "").lower()
    if m.startswith("local:"):
        return "local"
    if any(k in m for k in ("haiku", "mini", "flash")):
        return "cloud_fast"
    return "cloud_frontier"


def tier_factor(run_tier: str | None, target_tier: str | None) -> float:
    """How much a run on one model tier says about another: local never mixes with cloud."""
    if run_tier is None or target_tier is None or run_tier == target_tier:
        return 1.0
    if "local" in (run_tier, target_tier):
        return float(P["tier_factor_local_vs_cloud"])
    return float(P["tier_factor_fast_vs_frontier"])


def learn(
    wid: str,
    features: set[str],
    guess: float,
    measured: list[dict],
    tier: str | None = None,
    discipline: str | None = None,
) -> Learned | None:
    """`measured`: {id, features, diff (points), pairs, tier?, discipline?, valid?} for each
    finished run. `tier` and `discipline` are the target's: runs on another tier or bench
    discipline weigh less (learned-priors). A run with valid False isn't evidence and is skipped.
    Below min_learned_pairs valid pairs it stays the guess (basis "shape"). None if no run is
    similar enough to say anything."""
    k = P["guess_weight_pairs"]
    need = int(P["min_learned_pairs"])
    num, den, runs, pairs, ignored = k * guess, float(k), 0, 0, 0
    for m in measured:
        if m["pairs"] < P["min_pairs"] or m["diff"] is None:
            continue
        sim = 1.0 if m["id"] == wid else similarity(features, m["features"])
        if sim < P["min_similarity"]:
            continue
        w = sim * m["pairs"] * tier_factor(m.get("tier"), tier)
        if discipline is not None and m.get("discipline") not in (None, discipline):
            w *= P["discipline_factor"]
        if w <= 0:
            continue
        if m.get("valid") is False:
            ignored += 1
            continue
        num += w * m["diff"]
        den += w
        runs += 1
        pairs += m["pairs"]
    if not runs and not ignored:
        return None
    if pairs < need:
        return Learned(guess, guess, runs, pairs, "shape", need, ignored)
    return Learned(round(num / den, 1), guess, runs, pairs, "learned", need, ignored)


def cost_per_solved(trials: list, source_cost) -> dict:
    """Spend and tasks solved on each arm, and the cost of each extra task solved.
    `source_cost(t)` is what a reused trial cost when it ran."""
    out: dict = {}
    for arm in ("with", "without"):
        mine = [t for t in trials if t.arm == arm and t.outcome in ("pass", "fail")]
        spent = sum(source_cost(t) if t.reused_from is not None else t.cost_usd for t in mine)
        solved = sum(t.outcome == "pass" for t in mine)
        out[arm] = {
            "spent_usd": round(spent, 4),
            "solved": solved,
            "tasks": len(mine),
            "per_solved_usd": round(spent / solved, 4) if solved else None,
        }
    w, wo = out["with"], out["without"]
    # Per trial, so arms with a different number of finished trials compare fairly.
    if w["tasks"] and wo["tasks"]:
        extra_solved = w["solved"] / w["tasks"] - wo["solved"] / wo["tasks"]
        extra_spent = w["spent_usd"] / w["tasks"] - wo["spent_usd"] / wo["tasks"]
        out["per_extra_solved_usd"] = (
            round(extra_spent / extra_solved, 4) if extra_solved > 0 else None
        )
    else:
        out["per_extra_solved_usd"] = None
    return out
