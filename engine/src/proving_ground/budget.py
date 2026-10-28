"""Keep a run to its budget: predict the next trial's cost and reserve it before it starts.

Rules and values: the trial-budget skill. Nothing here calls a model.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from pathlib import Path

from proving_ground import skills
from proving_ground.stats import noise_half_width, pairs_for_half_width
from proving_ground.trial import Arm, TrialOutcome

B = skills.load("trial-budget").values
W = skills.load("workflow-patterns").values
ARMS: tuple[Arm, Arm] = ("with", "without")


def in_trial_option(agent: str) -> str | None:
    """The Harbor agent option that makes this agent stop itself at a dollar amount, if any."""
    return B["in_trial_cap"].get(agent)


def prior_usd(model: str) -> dict[Arm, float]:
    """What a trial is guessed to cost with nothing measured: the baseline model's prior, scaled
    by this model's relative cost (workflow-patterns). Models it doesn't list cost as the baseline."""
    models = W["models"]
    base = models[W["baseline_model"]]["cost"]
    scale = models.get(model, {}).get("cost", base) / base
    return {arm: float(B["prior_usd"][arm]) * scale for arm in ARMS}


def evidence(trials: list[TrialOutcome]) -> dict[Arm, list[float]]:
    """Costs that say what a trial costs: run here (not reused) and priced (above zero)."""
    out: dict[Arm, list[float]] = {"with": [], "without": []}
    for t in trials:
        if t.reused_from is None and t.cost_usd > 0 and t.arm in out:
            out[t.arm].append(t.cost_usd)
    return out


def history(store, root: Path, eid: int, model: str, agent: str) -> dict[Arm, list[float]]:
    """Earlier runs on this store (a bench) with the same agent and model: any treatment's
    "without" trials; the same treatment's "with" trials, else any treatment's."""
    from proving_ground.baseline import meta

    me = store.get_experiment(eid)
    tier = meta(root, eid).get("tier", "standard")
    return earlier(store, root, me.project_id, model, agent, me.treatment_name, eid, tier)


def _priced(trials: list[TrialOutcome]) -> dict[Arm, list[float]]:
    """An earlier run's trials that say what a trial costs: run there, ran to an answer (not
    errored or broken) and priced. Its validity doesn't matter: a run that isn't evidence for
    the change is still evidence for the cost."""
    return evidence([t for t in trials if t.outcome in ("pass", "fail")])


def _by_model(
    store,
    root: Path,
    project_id: int,
    agent: str,
    treatment: str,
    skip: int | None,
    tier: str | None = None,
) -> dict[str, dict[str, list[float]]]:
    """Earlier trials' costs per model: "with" of this treatment, "with" of any other, "without".
    With `tier`, only runs on that tier of a bench (bench-difficulty): a hard task costs more."""
    from proving_ground.baseline import meta

    out: dict[str, dict[str, list[float]]] = {}
    for e in store.list_experiments(project_id):
        m_ = meta(root, e.id)
        if e.id == skip or m_.get("agent", "claude-code") != agent:
            continue
        if tier is not None and m_.get("tier", "standard") != tier:
            continue
        got = _priced(store.trials(e.id))
        m = out.setdefault(e.model, {"same": [], "other": [], "without": []})
        m["without"] += got["without"]
        m["same" if e.treatment_name == treatment else "other"] += got["with"]
    return out


def _pick(m: dict[str, list[float]]) -> dict[Arm, list[float]]:
    return {"with": m["same"] or m["other"], "without": m["without"]}


def earlier(
    store,
    root: Path,
    project_id: int,
    model: str,
    agent: str,
    treatment: str,
    skip: int | None = None,
    tier: str | None = None,
) -> dict[Arm, list[float]]:
    """history() for a run that hasn't started yet (or skipping run `skip`): this model only."""
    got = _by_model(store, root, project_id, agent, treatment, skip, tier).get(model)
    return _pick(got) if got else {"with": [], "without": []}


def model_label(model: str) -> str:
    return W["models"].get(model, {}).get("label", model)


def _cost(model: str) -> float:
    base = W["models"][W["baseline_model"]]["cost"]
    return float(W["models"].get(model, {}).get("cost", base))


def measured(
    store,
    root: Path,
    project_id: int,
    model: str,
    agent: str,
    treatment: str,
    skip: int | None = None,
    tier: str | None = None,
) -> tuple[dict[Arm, list[float]], dict[Arm, str]]:
    """What earlier trials on this bench say a trial costs, before a run: this model's (as
    earlier()), and for an arm with none on it, other models' trials scaled by their relative
    cost (workflow-patterns), with a note naming the models they were measured on."""
    by = _by_model(store, root, project_id, agent, treatment, skip, tier)
    out = _pick(by[model]) if model in by else {"with": [], "without": []}
    notes: dict[Arm, str] = {}
    for arm in ARMS:
        if out[arm]:
            continue
        scaled, used = [], []
        for other in sorted(m for m in by if m != model):
            costs = _pick(by[other])[arm]
            if costs:
                scaled += [c * _cost(model) / _cost(other) for c in costs]
                used.append(model_label(other))
        if scaled:
            out[arm] = scaled
            notes[arm] = f"on {' and '.join(used)}, scaled to {model_label(model)} by relative cost"
    return out, notes


def status_text(status: str) -> str:
    """A run's status in words (trial-budget: status_words), never the raw value."""
    return B["status_words"].get(status, status.replace("_", " ").capitalize())


def cap_record() -> dict:
    """What a run's meta.json keeps about the cap it ran under (see overspend)."""
    return {"predict": B["predict"], "margin": float(B["margin"])}


def overspend(spent: float, budget: float | None, meta: dict, created_at: str) -> dict | None:
    """None when the run kept to its budget; else by how much it went over and why, in words."""
    if budget is None or spent <= budget + 0.005:
        return None
    by = spent - budget
    before = "budget_cap" not in meta and created_at < str(B["cap_since"])
    return {
        "by_usd": round(by, 4),
        "before_cap": before,
        "note": B["over_before_cap"] if before else B["over"].format(by=f"${by:.2f}"),
    }


def budget_for(pairs: int, per_pair: float) -> float:
    """The "Stop at" amount that pays for `pairs` at the predicted cost, rounded up to the
    budget field's step (trial-budget: budget_step_usd)."""
    step = float(B["budget_step_usd"])
    return round(math.ceil(pairs * per_pair / step - 1e-9) * step, 2)


def detectable_pts(pairs: int) -> int | None:
    """The smallest change, in whole pts, that `pairs` can tell from noise at `detect_base_rate`:
    the 95% interval's half-width (stats.noise_half_width), rounded up so that it is the inverse
    of the sizing: detectable_pts(n) <= t exactly when n >= pairs_to_detect(t). None for no pairs."""
    if pairs <= 0:
        return None
    hw = noise_half_width(pairs, float(B["detect_base_rate"]))
    return math.ceil(100 * hw - 1e-9)  # 1e-9: float noise, not a pt


def pairs_to_detect(pts: float) -> int:
    """The fewest pairs that tell a ±`pts` change from noise at `detect_base_rate` (the sizing)."""
    return pairs_for_half_width(pts / 100, float(B["detect_base_rate"]))


def _reach(pairs: int, per_pair: float, budget: float | None) -> int:
    """How many of `pairs` the budget pays for at `per_pair` (all of them with no budget)."""
    if budget is None or per_pair <= 0:
        return pairs
    return min(pairs, int((budget + 1e-9) // per_pair))


def full_pairs(
    tasks: int, per_pair: float, budget: float | None, base: int, sized: int | None = None
) -> int:
    """A full run's planned pairs on one bench or repo (trial-budget): at least `base` (trial_count),
    growing to as many as the budget pays for at `per_pair`, up to the pairs sized for
    `detect_target_pts` (or `sized`: a saving metric's guard, rig-score metric.plan), in whole
    repeats of the `tasks`. A free run grows to the sizing."""
    if tasks <= 0:
        return 0
    target = sized if sized is not None else pairs_to_detect(int(B["detect_target_pts"]))
    want = max(base, _reach(target, per_pair, budget))
    return math.ceil(want / tasks) * tasks


def per_pair(costs: CostModel) -> float:
    """One pair's predicted cost before a run: both arms, as the budget check predicts them."""
    return costs.estimate("with", [])[0] + costs.estimate("without", [])[0]


def probe_price(costs: CostModel, tasks: int) -> dict:
    """A baseline check's price (bench-difficulty: probe): one "without" trial per task, each as
    the budget check predicts it, and the budget that caps it there (rounded up to the step)."""
    each, source = costs.estimate("without", [])
    return {
        "trials": tasks,
        "per_trial": round(each, 4),
        "source": source,
        "total_usd": round(each * tasks, 4),
        "budget": 0.0 if costs.free else budget_for(tasks, each),
        "free": costs.free,
    }


def cant_start(costs: CostModel, budget: float) -> str | None:
    """Why a run can't start at all (trial-budget: cant_start), or None. The cheapest first step
    is one "with" trial, the "without" being possibly reused, so only that is held to the budget;
    the check before each pair still holds the rest of the run to it."""
    need, source = costs.estimate("with", [])
    if costs.free or need <= budget:
        return None
    # Up to the cent for what's needed, so raising it to that amount does start; a budget under
    # a cent keeps its digits rather than reading "$0.00".
    up = math.ceil(need * 100 - 1e-9) / 100
    said = f"${budget:.2f}" if budget >= 0.01 else f"${budget:.3g}"
    return B["cant_start"].format(budget=said, need=f"${up:.2f}", source=source)


def _like_pilot(reach: int, planned: int, pilot_pairs: int | None) -> bool:
    """A full run the budget stops within the pilot's pairs: no better than the pilot."""
    return pilot_pairs is not None and 0 < pilot_pairs < planned and reach <= pilot_pairs


def full_size(reach: int, planned: int, pilot_pairs: int | None = None) -> dict:
    """The run-size choice's "Full" label (trial-budget: full_label): a full run of `planned`
    pairs that the budget lets reach `reach`, and what those can tell from noise."""
    pts = detectable_pts(reach)
    if reach <= 0:
        state = "nothing"
    elif _like_pilot(reach, planned, pilot_pairs):
        state = "like_pilot"
    elif reach >= pairs_to_detect(int(B["detect_target_pts"])):
        state = "conclusive"
    else:
        state = "detects"
    return {
        "state": state,
        "pairs": reach,
        "planned_pairs": planned,
        "pts": pts,
        "text": B["full_label"][state].format(pairs=_pairs_text(reach), pts=pts),
    }


def forecast(
    costs: CostModel,
    pairs: int,
    budget: float | None = None,
    pilot_pairs: int | None = None,
    full: int | None = None,
    grows: bool = False,
) -> dict:
    """Before a run: what each arm's trial is predicted to cost (as the budget check predicts
    it, margin included), the whole run, how many pairs the budget pays for, what that can
    detect, and what it takes to detect a `detect_target_pts` change (trial-budget). With
    `full` (a full run's pairs), also what that would buy (full_size), whatever the size.
    `grows`: this is a full run whose pairs grow with the budget (full_pairs), so a budget
    alone can reach the sizing."""
    w, w_src = costs.estimate("with", [])
    wo, wo_src = costs.estimate("without", [])
    pair = w + wo
    base = float(B["detect_base_rate"])
    out = {
        "pairs": pairs,
        "trials": 2 * pairs,
        "per_trial": {"with": round(w, 4), "without": round(wo, 4)},
        "source": {"with": w_src, "without": wo_src},
        "measured_trials": {arm: 0 if costs.free else len(costs.earlier[arm]) for arm in ARMS},
        "per_pair": round(pair, 4),
        "total_usd": round(pair * pairs, 4),
        "free": costs.free,
    }
    if budget is not None:
        out["pairs_in_budget"] = _reach(pairs, pair, budget)
    reach = out.get("pairs_in_budget", pairs)
    out["detect"] = (
        {"pairs": reach, "pts": detectable_pts(reach), "base_rate": base} if reach > 0 else None
    )
    target = int(B["detect_target_pts"])
    need = pairs_to_detect(target)
    out["sizing"] = {
        "target_pts": target,
        "pairs": need,
        "usd": None if costs.free else budget_for(need, pair),
        "planned_pairs": pairs,
        "planned_pts": detectable_pts(pairs),
        "enough_planned": pairs >= need or grows,
        "enough_budget": reach >= need,
    }
    out["no_better_than_pilot"] = (
        B["no_better_than_pilot"].format(budget=f"${budget:.2f}", pairs=_pairs_text(reach))
        if budget is not None and _like_pilot(reach, pairs, pilot_pairs)
        else None
    )
    if full is not None:
        out["full"] = full_size(_reach(full, pair, budget), full, pilot_pairs)
    return out


def _pairs_text(n: int) -> str:
    return f"{n} pair" if n == 1 else f"{n} pairs"


@dataclass
class CostModel:
    """Predicts one trial's cost on an arm: this run's own trials first, then `earlier`
    (history), then `prior`. Free (a local model): always 0."""

    prior: dict[Arm, float]
    earlier: dict[Arm, list[float]] = field(default_factory=lambda: {"with": [], "without": []})
    free: bool = False
    # Per arm, where earlier costs came from when not this model (measured(): "on Sonnet 5.5, scaled ...").
    notes: dict = field(default_factory=dict)
    predict: str = B["predict"]
    margin: float = float(B["margin"])

    def __post_init__(self) -> None:
        if self.predict not in ("mean", "max"):
            raise ValueError(f"trial-budget predict must be mean or max, not {self.predict!r}")

    def estimate(self, arm: Arm, observed: list[float]) -> tuple[float, str]:
        """(predicted USD, where it came from)."""
        if self.free:
            return 0.0, "a local model"
        n = len(self.earlier[arm])
        said = f"measured on {n} earlier {'trial' if n == 1 else 'trials'}"
        for costs, source in (
            (observed, "from this run's trials"),
            (self.earlier[arm], f"{said} {self.notes[arm]}" if arm in self.notes else said),
        ):
            if costs:
                center = max(costs) if self.predict == "max" else sum(costs) / len(costs)
                return max(center * self.margin, max(costs)), source
        return self.prior[arm] * self.margin, "a first guess: nothing measured yet"


@dataclass
class Reservation:
    amount: float
    open: bool = True


class Ledger:
    """Spent and reserved dollars against one budget. Safe to use from several threads."""

    def __init__(self, budget: float, spent: float = 0.0):
        self.budget = budget
        self.spent = spent
        self.reserved = 0.0
        self._lock = threading.Lock()

    def free(self) -> float:
        """Neither spent nor reserved."""
        with self._lock:
            return self.budget - self.spent - self.reserved

    def reserve(self, amounts: list[float]) -> list[Reservation] | None:
        """Reserve all of them, or none: None when they don't fit together."""
        with self._lock:
            if self.spent + self.reserved + sum(amounts) > self.budget + 1e-9:
                return None
            self.reserved += sum(amounts)
            return [Reservation(a) for a in amounts]

    def claim(self, r: Reservation) -> float:
        """Grow a reservation by everything free and return it: the cap for a trial starting now.
        Held by that trial until it settles, so nothing running alongside can spend it too."""
        with self._lock:
            extra = max(0.0, self.budget - self.spent - self.reserved)
            r.amount += extra
            self.reserved += extra
            return r.amount

    def fits(self, r: Reservation) -> bool:
        """Can the trial holding `r` still start: is nothing overspent against it?"""
        with self._lock:
            return self.spent + self.reserved <= self.budget + 1e-9 and r.open

    def settle(self, r: Reservation, cost: float) -> None:
        """The trial is over: drop its reservation, add what it really cost."""
        with self._lock:
            if r.open:
                self.reserved -= r.amount
                r.open = False
            self.spent += cost

    def release(self, r: Reservation) -> None:
        self.settle(r, 0.0)
