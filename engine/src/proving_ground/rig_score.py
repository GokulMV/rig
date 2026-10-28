"""The Rig score: one number from 0 to 100 that says whether a skill or workflow works.

Rules, weights, thresholds, bands and wording: the rig-score skill. `rig_score` is pure: the
same evidence gives the same score. The `evidence_*` helpers turn the engine's result rows into
that evidence, and `ledger` counts a result's trials once for every line that cites them.
Nothing here calls a model or reads a file.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any, NamedTuple

from proving_ground import skills, stats

R = skills.load("rig-score").values
P = R["parts"]
T = R["text"]
G = R["gates"]
VD = R["verdict"]
VT = VD["text"]
ORDER = tuple(P)  # lift, cost, followed, holds_up, reliable


def _half_up(x: float) -> int:
    return math.floor(x + 0.5)


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


def _n(x: float) -> str:
    """A part's score in the formula: whole numbers bare, else one decimal."""
    r = round(x, 1)
    return f"{r:.0f}" if r == int(r) else f"{r:.1f}"


def _word(n: int, one: str) -> str:
    return one if n == 1 else f"{one}s"


# ---------- the trial ledger: one count per result, cited by every line ----------


def ledger(trials: Iterable, logs_read: int | None = None) -> dict:
    """Every count a result's lines cite, from one list of trials: total, each arm, complete
    pairs (as the interval counts them), clean / errored / broken, and how many "with" trials'
    session logs could be read (None when nothing reads them)."""
    trials = list(trials)
    s = stats.summarize(trials)
    return {
        "total": len(trials),
        "with": sum(t.arm == "with" for t in trials),
        "without": sum(t.arm == "without" for t in trials),
        "pairs": s.headline.n_pairs if s.headline else 0,
        "logs_read": logs_read,
        "clean": sum(t.outcome in ("pass", "fail") and not t.timed_out for t in trials),
        "timed_out": sum(t.timed_out for t in trials),
        "errored": s.errored,
        "broken": s.broken,
    }


def ledger_text(ld: dict, kind: str | None = None) -> str:
    """The ledger in one line: "5 trials (3 with, 2 without) · 2 complete pairs · ..."."""
    T = words(kind).t
    bad = ld.get("errored", 0) or ld.get("broken", 0)
    t = T["ledger"]
    return t.format(
        total=ld["total"],
        trials_word=_word(ld["total"], "trial"),
        arms=T["ledger_arms"].format(with_=ld["with"], without=ld["without"])
        if ld.get("with") is not None
        else "",
        pairs=ld.get("pairs", 0),
        pairs_word=_word(ld.get("pairs", 0), "pair"),
        clean=ld.get("clean", 0),
        timed=T["ledger_timed"].format(timed_out=ld["timed_out"]) if ld.get("timed_out") else "",
        bad=T["ledger_bad"].format(errored=ld.get("errored", 0), broken=ld.get("broken", 0))
        if bad
        else "",
        logs=T["ledger_logs"].format(read=ld["logs_read"], with_=ld["with"])
        if ld.get("logs_read") is not None and ld.get("with") is not None
        else "",
    )


def _ledger_of(ev: dict) -> dict:
    """The evidence's ledger; older evidence carries only {total, errored, broken}."""
    if ev.get("ledger"):
        return ev["ledger"]
    tr = ev.get("trials") or {}
    total = int(tr.get("total") or 0)
    errored, broken = int(tr.get("errored") or 0), int(tr.get("broken") or 0)
    return {
        "total": total,
        "with": tr.get("with"),
        "without": tr.get("without"),
        "pairs": int(ev.get("n_pairs") or 0),
        "logs_read": None,
        "clean": total - errored - broken,
        "errored": errored,
        "broken": broken,
    }


# ---------- the five parts: each (score 0-100 or None, detail, drag or None) ----------


def lift(ev: dict) -> tuple[float, str, str | None]:
    T = words(ev).t
    low = (ev.get("ci_low") or 0.0) * 100
    target = float(P["lift"]["target_pts"])
    score = _clamp(low / target * 100)
    key = "detail_items" if ev.get("quality") == "items" else "detail"
    detail = T["lift"][key].format(low=low, target=target)
    if ev.get("verdict") == "hurts":
        drag = T["lift"]["hurts"].format(diff=(ev.get("diff") or 0.0) * 100)
    elif low <= 0:
        drag = T["lift"]["none"]
    else:
        drag = T["lift"]["low"].format(low=low)
    return score, detail, drag


def _per(arm: dict, per_solved: bool) -> float:
    return arm["spent_usd"] / (arm["solved"] if per_solved else arm["tasks"])


def cost(ev: dict) -> tuple[float | None, str, str | None]:
    T = words(ev).t
    c = ev.get("costs") or {}
    w, wo = c.get("with") or {}, c.get("without") or {}
    if ev.get("local"):
        return 100.0, T["cost"]["free"], None
    # Unpriced (a cost of 0 on a model that isn't local): nothing to compare.
    if not w.get("tasks") or not wo.get("tasks") or min(w["spent_usd"], wo["spent_usd"]) <= 0:
        return None, T["cost"]["unknown"], None
    per_solved = w.get("solved", 0) > 0 and wo.get("solved", 0) > 0
    ratio = _per(w, per_solved) / _per(wo, per_solved)
    full, zero = float(P["cost"]["full"]), float(P["cost"]["zero"])
    if ratio <= full:
        score = 100.0
    elif ratio >= zero:
        score = 0.0
    else:
        score = 100 * (math.log(zero) - math.log(ratio)) / (math.log(zero) - math.log(full))
    basis = "solved task" if per_solved else "task"
    return (
        score,
        T["cost"]["detail"].format(ratio=ratio, basis=basis),
        T["cost"]["drag"].format(ratio=ratio),
    )


def followed(ev: dict) -> tuple[float | None, str, str | None]:
    t = T["followed"]
    if ev.get("kind") == "workflow":
        a = ev.get("adherence") or {}
        if not a.get("read") or a.get("steps_run") is None:
            return None, t["unknown"], None
        run, ok = float(a["steps_run"]), float(a.get("models_ok") or 0.0)
        share = float(P["followed"]["steps_share"])
        score = _clamp(100 * (share * run + (1 - share) * ok))
        steps, read = a.get("steps"), int(a["read"])
        trials = _word(read, "trial")
        if steps:
            detail = t["workflow"].format(
                run=round(run * steps),
                steps=steps,
                models=round(ok * steps),
                read=read,
                trials=trials,
            )
            skipped, wrong = round((1 - run) * steps), round((run - ok) * steps)
            if skipped:
                drag = t["drag_skipped"].format(skipped=skipped, steps=steps)
            elif wrong:
                drag = t["drag_models"].format(wrong=wrong)
            else:
                drag = None
        else:
            detail = t["workflow_unsized"].format(
                run_pct=run * 100, models_pct=ok * 100, read=read, trials=trials
            )
            drag = (
                t["drag_skipped_unsized"].format(skipped_pct=(1 - run) * 100) if run < 1 else None
            )
        return score, detail, drag
    if ev.get("kind") in ("hook", "instructions", "before_after"):  # no signal: never guessed
        return None, t[ev["kind"]], None
    o = ev.get("opened") or {}
    if not o.get("read"):
        return None, t["unknown"], None
    read, opened = int(o["read"]), int(o.get("opened") or 0)
    missed = read - opened
    trials = _word(read, "trial")
    said, drag = ("mcp", "drag_mcp") if ev.get("kind") == "mcp" else ("skill", "drag_skill")
    return (
        100 * opened / read,
        t[said].format(opened=opened, read=read, trials=trials),
        t[drag].format(missed=missed, read=read, trials=trials) if missed else None,
    )


def holds_up(ev: dict) -> tuple[float | None, str, str | None]:
    v = ev.get("holds_up")
    t = T["holds_up"]
    if v == "unclear":  # not measured: why, in words
        return None, t[f"unclear_{ev.get('holds_up_why') or 'mixed'}"], None
    if v not in P["holds_up"]["scores"]:
        return None, t["unknown"], None
    drag = t["drag_overfit"] if v == "overfit" else None
    return float(P["holds_up"]["scores"][v]), t[v], drag


def reliable(ev: dict) -> tuple[float | None, str, str | None]:
    ld = _ledger_of(ev)
    total = int(ld.get("total") or 0)
    t = words(ev).t["reliable"]
    if not total:
        return None, t["unknown"], None
    clean = int(ld.get("clean") or 0)
    bad = total - clean
    score = 100 * clean / total
    if ld.get("with") is None:  # older evidence: no split by arm
        detail = t["detail"].split(" (")[0].format(clean=clean, total=total)
    else:
        detail = t["detail"].format(
            clean=clean, total=total, with_=ld["with"], without=ld["without"]
        )
    drag = t["drag"].format(bad=bad, total=total) if bad else None
    judge = ev.get("judge")
    if judge is not None and not judge.get("trustworthy"):
        score *= float(P["reliable"]["untrusted_judge"])
        detail += t["judge"]
        drag = f"{drag}; {t['drag_judge']}" if drag else t["drag_judge"]
    return score, detail, drag


PARTS = {
    "lift": lift,
    "cost": cost,
    "followed": followed,
    "holds_up": holds_up,
    "reliable": reliable,
}


def _band(bid: str) -> dict:
    return next(b for b in R["bands"] if b["id"] == bid)


def _settle(ev: dict, pairs: int) -> str:
    """What would settle an interval that reaches 0: the pairs a lift this size needs."""
    diff, base = ev.get("diff"), ev.get("pass_without")
    if diff is None or diff <= 0:
        return T["settle_none"].format(pairs=pairs, pairs_word=_word(pairs, "pair"))
    need = stats.required_pairs(diff, base) if base is not None else None
    if need and need > pairs:
        return T["settle_pairs"].format(need=need, pairs=pairs)
    return T["settle_more"].format(pairs=pairs)


def _no_score(
    entry: dict, reason: str, pairs: int, parts: list[dict], ld: dict, kind: str | None = None
) -> dict:
    """No number: not evidence, or nothing measured yet. The caller adds the verdict."""
    for p in parts:
        p.pop("_raw"), p.pop("_drag")
        p["counted"] = False
    return {
        "score": None,
        "band": entry["id"],
        "tone": entry["tone"],
        "label": entry["label"],
        "reason": reason,
        "provisional": False,
        "pairs": pairs,
        "parts": parts,
        "gates": [],
        "formula": None,
        "ledger": ld,
        "ledger_text": ledger_text(ld, kind),
    }


def rig_score(evidence: dict) -> dict[str, Any]:
    """{score, band, tone, label, reason, provisional, pairs, parts, gates, formula, ledger}.

    `evidence`: kind: "workflow" | "skill"; n_pairs, diff, ci_low, ci_high (fractions), verdict,
    pass_without; validity: validity.judge()'s (absent: valid); costs: {with, without:
    {spent_usd, solved, tasks}}; local: bool; adherence: adherence.summarize() (+ steps) for a
    workflow; opened: {read, opened} for a skill; holds_up: "generalises" | "unclear" |
    "overfit" | None; ledger: ledger() (or the older trials: {total, errored, broken});
    judge: None (not judged) | {trustworthy: bool}.
    """
    ev = on_items(evidence)
    if metric_of(ev) is not None:  # tokens, cost or time: see Rules: Metric
        ev = _metric_validity(ev)
        out = _score_metric(ev)
        out["verdict"] = _verdict_metric(ev, out)
        out["quality"] = ev.get("quality", "pass_rate")
        out["metric"] = metric_summary(ev)
        return out
    out = _score(ev)
    out["verdict"] = verdict(ev, out)
    out["quality"] = ev.get("quality", "pass_rate")
    return out


def _items_usable(it: dict | None) -> bool:
    return bool(it and it.get("n") and it.get("ci_low") is not None and it.get("with") is not None)


def _items_edge(it: dict) -> str | None:
    """"ceiling" when both arms got every item right, "floor" when both got none, else None."""
    w, wo = it.get("with"), it.get("without")
    if w == wo == 1.0:
        return "ceiling"
    if w == wo == 0.0:
        return "floor"
    return None


def on_items(evidence: dict) -> dict:
    """The evidence judged on partial credit when the result row has `items`: the interval,
    verdict and both arms' scores become the item score's. A pass rate that can't move (both
    always pass, both always fail, each task the same both ways) is no longer uninformative
    when the item scores aren't at a ceiling or a floor: the items could still differ."""
    it = evidence.get("items")
    if not _items_usable(it):
        return evidence
    lo = it["ci_low"]
    hi = it["ci_high"] if it.get("ci_high") is not None else lo
    ev = evidence | {
        "quality": "items",
        "n_pairs": int(it["n"]),
        "diff": it.get("diff", it["with"] - it["without"]),
        "ci_low": lo,
        "ci_high": hi,
        "verdict": stats.verdict(lo, hi).value,
        "pass_with": it["with"],
        "pass_without": it["without"],
    }
    v = evidence.get("validity") or {}
    if v.get("status") == "uninformative" and _items_edge(it) is None:
        ev["validity"] = {"status": "valid", "badge": None, "reason": None, "cause": None}
    return ev


def _score(evidence: dict) -> dict[str, Any]:
    T = words(evidence).t
    pairs = int(evidence.get("n_pairs") or 0)
    ld = _ledger_of(evidence)
    valid = evidence.get("validity") or {}
    # Both always pass: the pass rate can't move, so only cost, time and reliability can say
    # anything, and only when they clearly differ (verdict.clearly).
    call = efficiency(evidence)["call"] if _ceiling(evidence) else None
    if call not in ("better", "worse"):
        call = None
    parts = []
    for pid in ORDER:
        score, detail, drag = PARTS[pid](evidence)
        if call and pid == "lift":
            score, detail, drag = None, T["ceiling"]["lift"], None
        parts.append(
            {
                "id": pid,
                "name": P[pid]["name"],
                "weight": P[pid]["weight"],
                "score": None if score is None else round(score, 1),
                "detail": detail,
                "_raw": score,
                "_drag": drag,
            }
        )
    if valid.get("status", "valid") != "valid" and call is None:
        why = ". ".join(x.rstrip(".") for x in (valid.get("badge"), valid.get("reason")) if x)
        why = why + "." if why else why
        return _no_score(
            R["not_evidence"],
            why or R["not_evidence"]["label"],
            pairs,
            parts,
            ld,
            evidence.get("kind"),
        )
    if pairs == 0 or evidence.get("ci_low") is None:
        return _no_score(R["none"], R["none"]["reason"], pairs, parts, ld, evidence.get("kind"))

    low = evidence["ci_low"] * 100
    high = (evidence.get("ci_high") if evidence.get("ci_high") is not None else 0.0) * 100
    # A cheaper or faster change at the same (always passing) result has shown its value.
    shown = low > 0 or call == "better"
    for p in parts:
        p["counted"] = p["_raw"] is not None
        if not shown and p["counted"] and p["id"] in R["credit_needs_lift"]:
            p["counted"] = False
            p["note"] = T["no_credit"]
    measured = [p for p in parts if p["_raw"] is not None]
    total_w = sum(p["weight"] for p in measured)
    weighted = sum(p["weight"] * p["_raw"] for p in measured if p["counted"])
    raw = weighted / total_w
    for p in parts:
        p["weight_used"] = round(p["weight"] / total_w, 4) if p["_raw"] is not None else 0.0

    gates = []
    capped = raw
    if evidence.get("verdict") == "hurts":
        capped = min(capped, G["hurts_cap"])
        gates.append(
            {
                "id": "hurts",
                "cap": G["hurts_cap"],
                "text": T["gates"]["hurts"].format(cap=G["hurts_cap"]),
            }
        )
    if call == "worse":
        capped = min(capped, G["ceiling_worse_cap"])
        gates.append(
            {
                "id": "ceiling_worse",
                "cap": G["ceiling_worse_cap"],
                "text": T["gates"]["ceiling_worse"].format(cap=G["ceiling_worse_cap"]),
            }
        )
    elif not shown:
        capped = min(capped, G["not_shown_cap"])
        gates.append(
            {
                "id": "not_shown",
                "cap": G["not_shown_cap"],
                "text": T["gates"]["not_shown"].format(cap=G["not_shown_cap"]),
            }
        )
    provisional = pairs < G["min_pairs"]
    if provisional:
        # Too few pairs to call it working: it can be promising, never "works".
        capped = min(capped, G["provisional_cap"])
        gates.append(
            {
                "id": "provisional",
                "cap": G["provisional_cap"],
                "text": T["gates"]["provisional"].format(
                    pairs=pairs, min=G["min_pairs"], cap=G["provisional_cap"]
                ),
            }
        )
    score = _half_up(capped)

    # Points each part costs (weight × shortfall of its own score); stable sort keeps part
    # order on ties.
    lost = sorted(
        (p for p in measured if p["_drag"] and p["_raw"] < 100),
        key=lambda p: -p["weight"] * (100 - p["_raw"]),
    )
    drags = [p for p in lost if p["_raw"] < R["drag_below"]][: R["max_reasons"]]
    top = lost[0] if lost else None

    # The band: from the evidence first; the number only places a lift that is shown.
    lift_drag = next(p["_drag"] for p in parts if p["id"] == "lift") or ""
    word = {}
    pw, pwo = evidence.get("pass_with"), evidence.get("pass_without")
    if call == "worse":
        what = _pieces(efficiency(evidence), worse_only=True)
        bid, word["drag"] = "doesnt", T["ceiling"]["worse"].format(what=what)
    elif call == "better":
        bid = (
            "works"
            if score >= _band("works")["min"]
            else "works_but"
            if score >= _band("works_but")["min"]
            else "not_proven"
            if provisional and capped < raw
            else "helps_but"
        )
        if bid == "works_but":
            word["noun"] = P[top["id"]]["noun"] if top else ""
        elif bid == "not_proven":
            word["settle"] = T["settle_more"].format(pairs=pairs)
        elif bid == "helps_but":
            word["drag"] = top["_drag"] if top else ""
    elif pwo is not None and pwo >= 1 and pw is not None and pw < 1:
        # The plain agent passes every task: no lift is possible on this bench.
        bid, word["drag"] = "doesnt", T["baseline_ceiling"]
    elif evidence.get("verdict") == "hurts":
        bid, word["drag"] = "doesnt", lift_drag
    elif high <= 0:
        bid, word["drag"] = "doesnt", T["no_lift"].format(high=high)
    elif high < R["doesnt_below_pts"]:
        bid = "doesnt"
        word["drag"] = T["cant_reach"].format(pts=R["doesnt_below_pts"], high=high)
    elif not shown:
        bid, word["settle"] = "not_proven", _settle(evidence, pairs)
    elif score >= _band("works")["min"]:
        bid = "works"
    elif score >= _band("works_but")["min"]:
        bid, word["noun"] = "works_but", P[top["id"]]["noun"] if top else ""
    elif provisional and capped < raw:  # held back by the pair count alone
        bid, word["settle"] = "not_proven", T["settle_more"].format(pairs=pairs)
    else:
        bid, word["drag"] = "helps_but", top["_drag"] if top else lift_drag
    if bid == "doesnt":  # the pair count capped how high it could go, not this answer
        for g in gates:
            if g["id"] == "provisional":
                g["text"] = T["gates"]["provisional_doesnt"].format(
                    pairs=pairs, min=G["min_pairs"]
                )
    band = _band(bid)
    label = band["label"].format(**({"noun": "", "settle": "", "drag": ""} | word))

    reason = "; ".join(p["_drag"] for p in drags) or (
        top["_drag"] if top and bid != "works" else R["works_reason"]
    )
    # Held back only by the pair count: say so, not "every part holds up".
    if provisional and not drags and capped < raw:
        reason = R["too_few_pairs"].format(pairs=pairs, min=G["min_pairs"])
    # "Every part holds up" must not pass over a part nobody measured.
    missing = [p["name"].lower() for p in parts if p["_raw"] is None]
    if missing and not drags:
        reason += "; " + R["unmeasured"].format(names=", ".join(missing))

    f = T["formula"]
    terms = [
        f["term"].format(weight=p["weight"] * 100, score=_n(p["_raw"]))
        if p["counted"]
        else f["term_no_credit"].format(weight=p["weight"] * 100, name=p["name"])
        for p in measured
    ]
    text = f["sum"].format(terms=" + ".join(terms), raw=weighted)
    if total_w < 1 - 1e-9:
        text = f["rescaled"].format(
            sum=text, measured=total_w * 100, names=", ".join(missing), norm=raw
        )
    for g in gates:  # a cap the number is already under changes nothing
        g["binding"] = g["cap"] < raw
    if capped < raw:
        cap = min(g["cap"] for g in gates if g["cap"] < raw)
        why = next(g["id"] for g in gates if g["cap"] == cap)
        text += "; " + f["capped"].format(cap=cap, why=f["why"][why])
    text += "; " + f["final"].format(score=score)
    for p in parts:
        p.pop("_raw"), p.pop("_drag")
    return {
        "score": score,
        "band": band["id"],
        "tone": band["tone"],
        "label": label,
        "reason": reason[0].upper() + reason[1:],
        "provisional": provisional,
        "pairs": pairs,
        "parts": parts,
        "gates": gates,
        "formula": {
            "text": text,
            "measured_weight": round(total_w, 4),
            "raw": round(raw, 2),
            "not_measured": missing,
        },
        "ledger": ld,
        "ledger_text": ledger_text(ld, evidence.get("kind")),
    }


# ---------- the verdict: one plain answer on every result ----------

# Two-sided 95% Student t quantiles by degrees of freedom (1-30); above that, the normal's.
_T95 = (12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179,
        2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064,
        2.060, 2.056, 2.052, 2.048, 2.045, 2.042)  # fmt: skip


def _t95(df: int) -> float:
    return _T95[df - 1] if 1 <= df <= len(_T95) else stats.Z95


def arms(trials: Iterable, cost_of=None) -> dict:
    """Per arm, over finished trials (pass or fail, timeouts included: they spent the money and
    the time): how many, mean cost and duration per trial, tasks solved, and how many timed out
    or errored. And per task finished in both arms, each arm's mean cost and duration: the pairs
    the "clearly" rule (verdict.clearly) compares. `cost_of(t)`: what a reused baseline trial
    cost when it ran (views.source_cost); any other trial costs its own cost_usd."""
    trials = list(trials)

    def cost_at(t) -> float:
        return cost_of(t) if cost_of is not None and t.reused_from is not None else t.cost_usd

    out: dict = {}
    per: dict[str, dict[str, list]] = {}
    for arm in ("with", "without"):
        mine = [t for t in trials if t.arm == arm]
        fin = [t for t in mine if t.outcome in ("pass", "fail")]
        costs = [cost_at(t) for t in fin]
        out[arm] = {
            "trials": len(fin),
            "all": len(mine),
            "solved": sum(t.outcome == "pass" for t in fin),
            "cost_usd": round(sum(costs) / len(fin), 6) if fin else None,
            "duration_s": round(sum(t.duration_s for t in fin) / len(fin), 1) if fin else None,
            "timed_out": sum(t.timed_out for t in fin),
            "errored": sum(t.outcome == "errored" for t in mine),
        }
        for t, c in zip(fin, costs, strict=True):
            per.setdefault(t.scenario_id, {}).setdefault(arm, []).append((c, t.duration_s))
    tasks = []
    for sid, a in per.items():
        if "with" in a and "without" in a:
            mean = {k: [sum(x[i] for x in v) / len(v) for i in (0, 1)] for k, v in a.items()}
            tasks.append(
                {
                    "id": sid,
                    "cost": [round(mean["with"][0], 6), round(mean["without"][0], 6)],
                    "duration": [round(mean["with"][1], 1), round(mean["without"][1], 1)],
                }
            )
    out["tasks"] = tasks
    return out


def pool_arms(rows: list[dict]) -> dict | None:
    """Several results' `arms` as one: counts added, means weighted by finished trials, tasks
    kept apart by bench."""
    got = [(r.get("bench") or str(i), r["arms"]) for i, r in enumerate(rows) if r.get("arms")]
    if not got:
        return None
    out: dict = {}
    for arm in ("with", "without"):
        a = [x[arm] for _, x in got]
        n = sum(x["trials"] for x in a)

        def mean(k: str, a=a, n=n) -> float | None:
            have = [x for x in a if x[k] is not None]
            return round(sum(x[k] * x["trials"] for x in have) / n, 6) if n and have else None

        out[arm] = {
            "trials": n,
            "all": sum(x["all"] for x in a),
            "solved": sum(x["solved"] for x in a),
            "cost_usd": mean("cost_usd"),
            "duration_s": mean("duration_s"),
            "timed_out": sum(x["timed_out"] for x in a),
            "errored": sum(x["errored"] for x in a),
        }
    out["tasks"] = [t | {"id": f"{b}/{t['id']}"} for b, x in got for t in x["tasks"]]
    return out


def _compare(ev_arms: dict, key: str, mean_key: str) -> dict | None:
    """with ÷ without on one measure: the ratio of the arms' means per trial (what is said) and
    whether it is clearly more or less (verdict.clearly: the per-task geometric mean ratio past
    `ratio` and its 95% t-interval clear of 1)."""
    w, wo = ev_arms["with"].get(mean_key), ev_arms["without"].get(mean_key)
    if not w or not wo or w <= 0 or wo <= 0:
        return None
    logs = [
        math.log(t[key][0] / t[key][1])
        for t in ev_arms.get("tasks") or []
        if t[key][0] > 0 and t[key][1] > 0
    ]
    n = len(logs)
    c = VD["clearly"]
    out = {"ratio": w / wo, "with": w, "without": wo, "n": n, "clearly": None}
    if n:
        m = sum(logs) / n
        half = (
            _t95(n - 1) * math.sqrt(sum((x - m) ** 2 for x in logs) / (n - 1) / n)
            if n > 1
            else math.inf
        )
        out |= {"geo": math.exp(m), "low": math.exp(m - half), "high": math.exp(m + half)}
        if n >= c["min_tasks"]:
            if out["geo"] >= c["ratio"] and out["low"] > 1:
                out["clearly"] = "more"
            elif out["geo"] <= 1 / c["ratio"] and out["high"] < 1:
                out["clearly"] = "less"
    return out


def efficiency(ev: dict) -> dict:
    """Cost, time and reliability with against without, and the call at equal quality:
    "better" (something clearly cheaper or faster, nothing clearly worse, not less reliable),
    "worse" (something clearly dearer or slower, nothing clearly better), "mixed" (one of each)
    or None (nothing clear)."""
    a = ev.get("arms")
    if not a:
        return {"cost": None, "time": None, "reliable": None, "call": None, "arms": None}
    cost = None if ev.get("local") else _compare(a, "cost", "cost_usd")
    time = _compare(a, "duration", "duration_s")
    w, wo = a["with"], a["without"]

    def bad(x: dict) -> float:
        return (x["timed_out"] + x["errored"]) / x["all"] if x["all"] else 0.0

    less_reliable = bad(w) - bad(wo) > VD["unreliable_by"]
    marks = [m["clearly"] for m in (cost, time) if m]
    better, worse = "less" in marks, "more" in marks or less_reliable
    call = "mixed" if better and worse else "better" if better else "worse" if worse else None
    return {"cost": cost, "time": time, "reliable": less_reliable, "call": call, "arms": a}


def _x(r: float) -> str:
    return f"{r:.0f}×" if r >= 10 else f"{r:.1f}×"


def _usd(v: float) -> str:
    return f"${v:.2f}" if v >= 0.1 else f"${v:.3f}"


def _secs(v: float) -> str:
    return f"{v:.0f} s" if v < 90 else f"{v / 60:.1f} min"


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + VT["and"] + items[-1]


def _notable(m: dict | None) -> str | None:
    """ "more" / "less" when a measure is clearly, or at least by `ratio`, different."""
    if not m:
        return None
    if m["clearly"]:
        return m["clearly"]
    r = VD["clearly"]["ratio"]
    return "more" if m["ratio"] >= r else "less" if m["ratio"] <= 1 / r else None


def _pieces(eff: dict, worse_only: bool = False, quality: str | None = None) -> str:
    """The reason's middle: "costs 22× more per trial, takes 9.6× as long and timed out on 3
    of 5". `worse_only`: only what counts against it."""
    out = []
    if quality:
        out.append(quality)
    c, t = eff.get("cost"), eff.get("time")
    for m, more, less in ((c, "costs_more", "costs_less"), (t, "slower", "faster")):
        d = _notable(m)
        if d == "more":
            out.append(VT[more].format(ratio=_x(m["ratio"])))
        elif d == "less" and not worse_only:
            out.append(VT[less].format(ratio=_x(1 / m["ratio"])))
    a = eff.get("arms")
    if a:
        w = a["with"]
        if w["timed_out"]:
            out.append(VT["timed_out"].format(k=w["timed_out"], n=w["all"]))
        if w["errored"]:
            out.append(VT["errored"].format(k=w["errored"], n=w["all"]))
    return _join(out)


def _quality(ev: dict) -> dict | None:
    """The quality measure the verdict judges on: partial credit (`items`) when the result has
    it, else the pass rate over complete pairs."""
    it = ev.get("items")
    if _items_usable(it):

        def say(arm: str, short: bool = False) -> str:
            right, total = it.get(f"right_{arm}"), it.get(f"total_{arm}")
            if total:
                key = "q_items_short" if short else "q_items"
                return VT[key].format(right=right, total=total)
            return VT["q_items_pct_short" if short else "q_items_pct"].format(pct=it[arm] * 100)

        diff = it.get("diff", it["with"] - it["without"])
        return {
            "with": it["with"],
            "without": it["without"],
            "diff": diff,
            "low": it.get("ci_low") if it.get("ci_low") is not None else diff,
            "high": it.get("ci_high") if it.get("ci_high") is not None else diff,
            "n": int(it["n"]),
            "say_with": say("with"),
            "say_without": say("without", short=True),
            "items": True,
        }
    n = int(ev.get("n_pairs") or 0)
    pw, pwo = ev.get("pass_with"), ev.get("pass_without")
    if not n or ev.get("ci_low") is None or pw is None or pwo is None:
        return None
    return {
        "with": pw,
        "without": pwo,
        "diff": ev.get("diff") if ev.get("diff") is not None else pw - pwo,
        "low": ev["ci_low"],
        "high": ev.get("ci_high") if ev.get("ci_high") is not None else ev["ci_low"],
        "n": n,
        "say_with": VT["q_pass"].format(won=round(pw * n), n=n),
        "say_without": VT["q_pass"].format(won=round(pwo * n), n=n),
        "items": False,
    }


def _facts(ev: dict, eff: dict, q: dict | None) -> list[str]:
    """Quality, cost, time, reliability: one line each, whatever the verdict."""
    VT = words(ev).vt
    out = []
    if q:
        line = VT["fact_quality"].format(with_=q["say_with"], without=q["say_without"])
        line += VT["fact_lift"].format(
            diff=q["diff"] * 100, low=q["low"] * 100, high=q["high"] * 100
        )
        out.append(line)
    a = eff.get("arms")
    if not a:
        return out
    c = eff.get("cost")
    if ev.get("local"):
        out.append(VT["fact_cost_free"])
    elif c:
        w, wo = a["with"], a["without"]
        solved = ""
        if w["solved"] and wo["solved"]:
            sw = w["cost_usd"] * w["trials"] / w["solved"]
            swo = wo["cost_usd"] * wo["trials"] / wo["solved"]
            solved = VT["fact_cost_solved"].format(
                with_=_usd(sw), without=_usd(swo), ratio=_x(sw / swo)
            )
        out.append(
            VT["fact_cost"].format(
                with_=_usd(c["with"]), without=_usd(c["without"]), ratio=_x(c["ratio"]),
                solved=solved,
            )
        )  # fmt: skip
    else:
        out.append(VT["fact_cost_unknown"])
    t = eff.get("time")
    out.append(
        VT["fact_time"].format(
            with_=_secs(t["with"]), without=_secs(t["without"]), ratio=_x(t["ratio"])
        )
        if t
        else VT["fact_time_unknown"]
    )

    def bad(x: dict) -> str:
        bits = [
            VT[k].format(k=x[f], n=x["all"])
            for k, f in (("bad_timed", "timed_out"), ("bad_errored", "errored"))
            if x[f]
        ]
        if not x["all"]:
            return VT["bad_empty"]
        return _join(bits) if bits else VT["bad_none"].format(n=x["all"])

    out.append(VT["fact_reliable"].format(w_bad=bad(a["with"]), wo_bad=bad(a["without"])))
    return out


def _ceiling(ev: dict) -> bool:
    """Both arms pass every task (evidence-validity both_pass) and partial credit, if any, is
    the same both ways: quality can't differ."""
    v = ev.get("validity") or {}
    if v.get("status") != "uninformative" or v.get("cause") != "both_pass":
        return False
    it = ev.get("items")
    return not _items_usable(it) or _items_edge(it) == "ceiling"


def verdict(ev: dict, rig: dict) -> dict:
    """{id: helps | doesnt | cant, word, tone, reason, next, facts}: the plain answer, its
    one-line reason naming the numbers, one next step, and the quality / cost / time /
    reliability lines. Never "helps" without a lift whose 95% lower bound is above 0 or a clear
    cost or time win at equal quality, on at least `gates.min_pairs` pairs."""
    VT = words(ev).vt
    noun = VD["noun"].get(ev.get("kind") or "change", VD["noun"]["change"])
    pairs = int(ev.get("n_pairs") or 0)
    need = int(G["min_pairs"])
    v = ev.get("validity") or {}
    status, cause = v.get("status", "valid"), v.get("cause")
    eff = efficiency(ev)
    q = _quality(ev)

    def out(vid: str, reason: str, step: str) -> dict:
        return {
            "id": vid,
            "word": VD["words"][vid],
            "tone": VD["tones"][vid],
            "reason": reason[0].upper() + reason[1:] if reason else reason,
            "next": VT["next"].format(step=step),
            "facts": _facts(ev, eff, q),
        }

    def fmt(key: str, **kw: Any) -> str:
        return VT[key].format(noun=noun, **kw)

    def extra() -> str:
        what = _pieces(eff)
        return f"; {what}" if what else ""

    if status == "invalid":
        if cause in ("broken_check", "not_applied", "mcp_unused"):
            return out("cant", fmt(cause), fmt(f"{cause}_next"))
        why = ". ".join(x.rstrip(".") for x in (v.get("badge"), v.get("reason")) if x)
        return out("cant", why + ".", fmt("not_evidence_next"))
    if _ceiling(ev):
        call = eff["call"]
        n = len((eff.get("arms") or {}).get("tasks") or [])
        if call == "worse":
            return out(
                "doesnt",
                fmt("ceiling_worse", what=_pieces(eff, worse_only=True)),
                fmt("ceiling_worse_next"),
            )
        if call == "better":
            if pairs < need:
                return out(
                    "cant",
                    fmt("few_pairs_efficiency", what=_pieces(eff), pairs=pairs, min=need),
                    fmt("few_pairs_next", more=need - pairs),
                )
            return out(
                "helps", fmt("helps_efficiency", what=_pieces(eff), n=n),
                fmt("helps_efficiency_next"),
            )  # fmt: skip
        if call == "mixed":
            return out("cant", fmt("ceiling_mixed", what=_pieces(eff)), fmt("ceiling_mixed_next"))
        what = _pieces(eff)
        if n < VD["clearly"]["min_tasks"] and what:
            return out(
                "cant",
                fmt(
                    "ceiling_few", what=what, n=n, tasks_word=_word(n, "task"),
                    min=VD["clearly"]["min_tasks"],
                ),
                fmt("ceiling_few_next"),
            )  # fmt: skip
        bits = [
            f"{_x(m['ratio'])} {label}"
            for m, label in ((eff.get("cost"), "the cost"), (eff.get("time"), "the time"))
            if m
        ]
        return out(
            "cant",
            fmt(
                "ceiling_unclear",
                what=_join(bits) or "no cost or time recorded",
                n=n,
                tasks_word=_word(n, "task"),
            ),
            fmt("ceiling_unclear_next"),
        )
    if status == "uninformative":
        key = cause if cause in ("both_fail", "each_same") else "each_same"
        return out("cant", fmt(key), fmt(f"{key}_next"))
    if q is None:
        return out("cant", fmt("no_pairs"), fmt("no_pairs_next"))
    nums = {
        "quality": q["say_with"],
        "quality_without": q["say_without"],
        "diff": q["diff"] * 100,
        "low": q["low"] * 100,
        "high": q["high"] * 100,
        "pairs": q["n"],
    }
    if q["without"] >= 1 and q["with"] < 1:
        a = (eff.get("arms") or {}).get("with") or {}
        fails = q["n"] - round(q["with"] * q["n"])
        if q["items"]:
            passes = VT["gets"].format(quality=q["say_with"])
        elif fails <= (a.get("timed_out") or 0) and a:
            passes = None  # every fail is a timeout: "timed out on 3 of 5" says it
        else:
            passes = VT["passes"].format(won=round(q["with"] * q["n"]), n=q["n"])
        what = _pieces(eff, worse_only=True, quality=passes)
        key = "baseline_ceiling_items" if q["items"] else "baseline_ceiling"
        return out("doesnt", fmt(key, what=what, **nums), fmt("baseline_ceiling_next"))
    if q["high"] < 0 or ev.get("verdict") == "hurts":
        return out("doesnt", fmt("hurts", extra=extra(), **nums), fmt("hurts_next"))
    if q["high"] * 100 < R["doesnt_below_pts"]:
        return out(
            "doesnt",
            fmt("too_small", pts=R["doesnt_below_pts"], extra=extra(), **nums),
            fmt("too_small_next"),
        )
    if q["low"] > 0:
        if q["n"] < need:
            return out(
                "cant",
                fmt("few_pairs", min=need, extra=extra(), **nums),
                fmt("few_pairs_next", more=need - q["n"]),
            )
        return out("helps", fmt("helps", extra=extra(), **nums), fmt("helps_next"))
    want = stats.required_pairs(q["diff"], q["without"]) if q["diff"] and q["diff"] > 0 else None
    step = (
        fmt("settle_next", need=want, pairs=q["n"])
        if want and want > q["n"]
        else fmt("more_next", pairs=q["n"])
    )
    return out("cant", fmt("not_settled", extra=extra(), **nums), step)


# ---------- evidence from the engine's rows ----------


def holds_up_verdict(row: dict) -> str | None:
    """generalises / unclear / overfit from a Lab row; None when the bench has no held-out tasks."""
    if row.get("overfit"):
        return row["overfit"]["verdict"]
    held = row.get("held_out")
    if not held:
        return None
    if held.get("diff") is None or not held.get("n_pairs"):
        return "unclear"
    vis = (row.get("visible") or {}).get("diff")
    if held["diff"] > 0:
        return "generalises"
    if vis is not None and vis * 100 >= R["overfit_visible_pts"]:
        return "overfit"
    return "unclear"


def holds_up_why(row: dict) -> str | None:
    """Why a row's held-out result is unclear: "no_pairs" (no held-out task ran in both arms),
    "no_gain" (nothing gained on the visible tasks to confirm) or "mixed"; None when it isn't."""
    if holds_up_verdict(row) != "unclear":
        return None
    held = row.get("held_out") or {}
    if held.get("diff") is None or not held.get("n_pairs"):
        return "no_pairs"
    vis = (row.get("visible") or {}).get("diff")
    return "no_gain" if vis is not None and vis <= 0 else "mixed"


def evidence_from_row(row: dict, kind: str = "workflow") -> dict:
    """A Lab results row (or a repo experiment shaped like one) as score evidence."""
    return {
        "kind": kind,
        "n_pairs": row.get("n_pairs") or 0,
        "diff": row.get("diff"),
        "ci_low": row.get("ci_low"),
        "ci_high": row.get("ci_high"),
        "verdict": row.get("verdict"),
        "pass_with": row.get("pass_with"),
        "pass_without": row.get("pass_without"),
        "validity": row.get("validity"),
        "costs": row.get("costs"),
        "arms": row.get("arms"),
        "items": row.get("items"),
        "local": bool(row.get("local")),
        "adherence": row.get("adherence"),
        "opened": row.get("opened"),
        "holds_up": holds_up_verdict(row),
        "holds_up_why": holds_up_why(row),
        "trials": row.get("trials"),
        "ledger": row.get("ledger"),
        "judge": row.get("judge"),
    } | ({"metric": row["metric"]} if row.get("metric") else {})


def pool_evidence(rows: list[dict], pooled: dict, metric: dict | None = None) -> dict:
    """One workflow over several benches: the pooled interval, every bench's costs, logs and
    trials added up. Held out: overfit anywhere is overfit; generalises only if every bench with
    held-out tasks generalises. Judge: untrustworthy if any judged bench's judge is. Validity:
    the pool is evidence only when every bench's result with pairs is. `metric`: the pooled
    saving (suite.pool_metric), scored on as a single run's is; then a bench where both arms
    always pass is evidence, as it is for a single run on a saving."""
    arms: dict[str, dict] = {
        arm: {"spent_usd": 0.0, "solved": 0, "tasks": 0} for arm in ("with", "without")
    }
    trials = {"total": 0, "errored": 0, "broken": 0}
    keys = ("total", "with", "without", "pairs", "clean", "timed_out", "errored", "broken")
    ld: dict = dict.fromkeys(keys, 0) | {"logs_read": None}
    not_valid = []
    read = run = ok = 0.0
    steps = set()
    holds, judges = [], []
    for r in rows:
        for arm in arms:
            got = (r.get("costs") or {}).get(arm) or {}
            for k in arms[arm]:
                arms[arm][k] += got.get(k) or 0
        for k in trials:
            trials[k] += (r.get("trials") or {}).get(k) or 0
        got_ld = _ledger_of(r)
        for k in keys:
            ld[k] += got_ld.get(k) or 0
        if got_ld.get("logs_read") is not None:
            ld["logs_read"] = (ld["logs_read"] or 0) + got_ld["logs_read"]
        if not r.get("n_pairs"):  # its errored trials count; nothing else was measured there
            continue
        a = r.get("adherence") or {}
        if a.get("read") and a.get("steps_run") is not None:
            read += a["read"]
            run += a["steps_run"] * a["read"]
            ok += (a.get("models_ok") or 0) * a["read"]
            steps.add(a.get("steps"))
        v = (_metric_validity(r) if metric else r).get("validity") or {}
        if v.get("status", "valid") != "valid":
            not_valid.append(f"{r.get('bench_name') or r.get('bench')}: {v.get('badge')}")
        h = holds_up_verdict(r)
        if h:
            holds.append(h)
        if r.get("judge") is not None:
            judges.append(r["judge"])
    hold = (
        None
        if not holds
        else "overfit"
        if "overfit" in holds
        else "generalises"
        if all(h == "generalises" for h in holds)
        else "unclear"
    )
    adh = (
        {
            "read": int(read),
            "steps_run": round(run / read, 2),
            "models_ok": round(ok / read, 2),
            "steps": steps.pop() if len(steps) == 1 else None,
        }
        if read
        else None
    )
    return {
        "kind": "workflow",
        "n_pairs": pooled.get("n_pairs") or 0,
        "diff": pooled.get("diff"),
        "ci_low": pooled.get("ci_low"),
        "ci_high": pooled.get("ci_high"),
        "verdict": pooled.get("verdict"),
        "pass_with": pooled.get("pass_with"),
        "pass_without": pooled.get("pass_without"),
        "arms": pool_arms([r for r in rows if r.get("n_pairs")]),
        "validity": {
            "status": "invalid",
            "badge": "Not evidence: it pools results that aren't",
            "reason": "; ".join(not_valid) + ".",
        }
        if not_valid
        else None,
        "costs": arms,
        "local": bool(rows) and all(r.get("local") for r in rows),
        "adherence": adh,
        "holds_up": hold,
        "trials": trials,
        "ledger": ld | {"pairs": pooled.get("n_pairs") or 0},
        "judge": None if not judges else {"trustworthy": all(j.get("trustworthy") for j in judges)},
    } | ({"metric": metric} if metric else {})


# ---------- the metric: tokens, cost or time per solved task (see Rules: Metric) ----------

M = R["metric"]
MT = M["text"]


# ---------- the words by kind of run (by_kind) ----------


class Words(NamedTuple):
    t: dict  # text
    vt: dict  # verdict.text
    mt: dict  # metric.text


def _overlay(base: dict, over: dict) -> dict:
    """`base` with each key of `over` replacing the one at the same place, nested dicts merged."""
    out = dict(base)
    for k, v in over.items():
        nested = isinstance(v, dict) and isinstance(base.get(k), dict)
        out[k] = _overlay(base[k], v) if nested else v
    return out


WORDS = {
    kind: Words(
        _overlay(T, w.get("text") or {}),
        _overlay(VT, (w.get("verdict") or {}).get("text") or {}),
        _overlay(MT, (w.get("metric") or {}).get("text") or {}),
    )
    for kind, w in (R.get("by_kind") or {}).items()
}


def words(ev: dict | str | None) -> Words:
    """The lines a run says, by its kind (evidence or the kind itself): a code change measured
    before and after says "after" and "before" (by_kind); every other run the lines above."""
    kind = ev.get("kind") if isinstance(ev, dict) else ev
    return WORDS.get(kind or "") or Words(T, VT, MT)


def metric_of(ev: dict) -> dict | None:
    """The evidence's metric when it isn't the pass rate; None for the pass rate."""
    m = ev.get("metric")
    return m if isinstance(m, dict) and m.get("id") not in (None, M["default"]) else None


def metric_rows(trials: Iterable, metric: str, cost_of=None) -> list[tuple[float, int, float, int]]:
    """(value with, solved with, value without, solved without) per complete pair the pass
    rate counts. `cost_of(t)`: what a reused baseline trial cost when it ran (views.source_cost)."""
    if metric not in M["ids"]:
        raise ValueError(f"unknown metric {metric!r}: one of {', '.join(M['ids'])}")

    def value(t) -> float:
        if metric == "tokens":
            return float(t.tokens_in + t.tokens_out)
        if metric == "cost":
            return cost_of(t) if cost_of is not None and t.reused_from is not None else t.cost_usd
        return float(t.duration_s)

    return [
        (
            value(g["with"]),
            int(g["with"].outcome == "pass"),
            value(g["without"]),
            int(g["without"].outcome == "pass"),
        )
        for g in stats.real_pairs(trials)
    ]


def metric_evidence(
    trials: Iterable, metric: str | None, cost_of=None, level: float = 0.95
) -> dict | None:
    """{id, n, with, without, ratio, low, high, solved_with, solved_without} for a run scored on
    tokens, cost or time per solved task, over the complete pairs the pass rate counts; None
    for the pass rate. `low`/`high`: the ratio's 95% bootstrap interval (None under
    `bootstrap.min_pairs` pairs; `high` None with a `low` when it has no upper end). With
    nothing to compare, `missing` says why ("unrecorded" or "unsolved") and nothing else is set.
    `cost_of(t)`: what a reused baseline trial cost when it ran (views.source_cost). `level`:
    a stricter interval, for auto-extend's stop rule."""
    if not metric or metric == M["default"]:
        return None
    return metric_of_groups(metric, [metric_rows(trials, metric, cost_of)], level)


def metric_of_groups(
    metric: str, groups: list[list[tuple[float, int, float, int]]], level: float = 0.95
) -> dict:
    """metric_evidence over pairs in groups (a suite: one group per bench): the figures are
    over every pair, the bootstrap resamples each group within itself (stats.
    stratified_ratio_ci). A group that recorded nothing on an arm makes the whole "unrecorded":
    a total missing one bench's values would be no total at all."""
    rows = [r for g in groups for r in g]
    out: dict = {"id": metric, "n": len(rows)}
    if not rows:
        return out
    if any(g and (sum(r[0] for r in g) <= 0 or sum(r[2] for r in g) <= 0) for g in groups):
        return out | {"missing": "unrecorded"}
    sw, swo = sum(r[1] for r in rows), sum(r[3] for r in rows)
    if not sw or not swo:
        return out | {"missing": "unsolved", "solved_with": sw, "solved_without": swo}
    b = M["bootstrap"]
    ratio, lo, hi = stats.stratified_ratio_ci(
        groups, b["resamples"], b["seed"], b["min_pairs"], level
    )
    return out | {
        "with": sum(r[0] for r in rows) / sw,
        "without": sum(r[2] for r in rows) / swo,
        "ratio": ratio,
        "low": lo,
        "high": None if hi is None or math.isinf(hi) else hi,
        "solved_with": sw,
        "solved_without": swo,
    }


def metric_stop(trials: Iterable, metric: str, z: float, cost_of=None) -> dict:
    """Auto-extend's stop rule on a saving (judge-experiment: Auto-extend), at the stricter
    interval `z` for both the saving and its guard. {why, waiting, pairs}: `why` is what decided
    it ("both": a cut shown and the guard met; "hurts": the pass rate shown lower; "worse": the
    measure shown higher; "too_small": the best cut under `doesnt_below_cut`; "unrecorded":
    nothing to compare, ever), or None while `waiting` names what isn't: "saving", "guard"."""
    trials = list(trials)
    m = metric_evidence(trials, metric, cost_of, stats.level_of(z)) or {}
    q = stats.stop_quality(trials, z)  # (low, high, pairs) of the guard's quality
    pairs = q[2] if q else 0

    def out(why: str | None, waiting: list[str] = ()) -> dict:
        return {"why": why, "waiting": list(waiting), "pairs": pairs}

    if m.get("missing") == "unrecorded":
        return out("unrecorded")
    if q is not None and q[1] < 0:
        return out("hurts")
    low, high = m.get("low"), m.get("high")
    if low is not None and low > 1:
        return out("worse")
    if low is not None and 1 - low < M["doesnt_below_cut"]:
        return out("too_small")
    cut = high is not None and high < 1
    holds = q is not None and q[0] * 100 > -float(M["margin_pts"])
    if cut and holds:
        return out("both")
    return out(None, [k for k, ok in (("saving", cut), ("guard", holds)) if not ok])


def _mval(mid: str, v: float) -> str:
    if mid == "tokens":
        return f"{v / 1000:.1f}k" if v >= 1000 else f"{v:.0f}"
    return _usd(v) if mid == "cost" else _secs(v)


def _signed(r: float | None) -> str:
    """A ratio as the change it is: 0.48 → "-52%"; None (no upper end) in words."""
    return MT["unbounded"] if r is None else f"{(r - 1) * 100:+.0f}%"


def _headline(m: dict, kind: str | None = None) -> str:
    """ "Tokens per solved task: with 21.4k vs without 44.1k (-52%, 95% interval -61% to -40%)"."""
    MT = words(kind).mt
    kw = {
        "name": M["names"][m["id"]],
        "with_": _mval(m["id"], m["with"]),
        "without": _mval(m["id"], m["without"]),
        "change": _signed(m["ratio"]),
    }
    if m.get("low") is None:
        return MT["headline_no_ci"].format(min=M["bootstrap"]["min_pairs"], **kw)
    return MT["headline"].format(low=_signed(m["low"]), high=_signed(m.get("high")), **kw)


def _guard(ev: dict, q: dict) -> str:
    """The pass rate as the guard: "Pass rate: 15 of 20 passed with vs ... (at worst -9 pts, within
    the 10-pt margin)"."""
    MT = words(ev).mt
    margin = M["margin_pts"]
    ok = q["low"] * 100 > -margin and ev.get("verdict") != "hurts"
    return MT["guard"].format(
        quality=MT["quality_items" if q["items"] else "quality_pass"],
        with_=q["say_with"],
        without=q["say_without"],
        diff=q["diff"] * 100,
        low=q["low"] * 100,
        within=MT["within" if ok else "past"].format(margin=margin),
    )


def _metric_validity(ev: dict) -> dict:
    """Both always pass (or each task the same both ways) says nothing about the pass rate, but
    it is exactly what the guard asks for: here it is evidence."""
    v = ev.get("validity") or {}
    if v.get("status") == "uninformative" and v.get("cause") in ("both_pass", "each_same"):
        return ev | {"validity": {"status": "valid", "badge": None, "reason": None, "cause": None}}
    return ev


def _metric_state(ev: dict) -> dict:
    """Everything the parts, gates, band and verdict decide on, in points and percent."""
    m = ev["metric"]
    margin = float(M["margin_pts"])
    q_low = (ev.get("ci_low") or 0.0) * 100
    q_diff = (ev.get("diff") or 0.0) * 100
    hurts = ev.get("verdict") == "hurts"
    has_ci = m.get("low") is not None
    # The cut is 1 - the ratio: its lower bound from the ratio's upper end (none: unbounded).
    cut_low = None if not has_ci else (-math.inf if m.get("high") is None else (1 - m["high"]) * 100)
    cut_high = None if not has_ci else (1 - m["low"]) * 100
    return {
        "m": m,
        "noun": M["nouns"][m["id"]],
        "kind": ev.get("kind"),
        "margin": margin,
        "q_low": q_low,
        "q_diff": q_diff,
        "hurts": hurts,
        "ni": q_low > -margin and not hurts,
        "cut_low": cut_low,
        "cut_high": cut_high,
        "cut": cut_low is not None and cut_low > 0,
        "worse": has_ci and m["low"] > 1,
    }


def _metric_lift(st: dict) -> tuple[float, str, str | None]:
    """Lift on the cut: its lower bound against `target_cut`; 0 until the pass rate holds."""
    T, MT = words(st["kind"]).t, words(st["kind"]).mt
    m, noun = st["m"], st["noun"]
    target = float(M["target_cut"]) * 100
    if st["cut_low"] is None:
        score = 0.0
        detail = MT["lift_detail_no_ci"].format(
            change=_signed(m["ratio"]), noun=noun, min=M["bootstrap"]["min_pairs"]
        )
    elif st["cut"]:
        score = _clamp(st["cut_low"] / target * 100)
        detail = MT["lift_detail"].format(low=st["cut_low"], target=target, noun=noun)
    else:
        score = 0.0
        detail = MT["lift_detail_none"].format(noun=noun, high=_signed(m.get("high")))
    if not st["ni"]:
        score = 0.0
        detail += MT["lift_held"]
    if st["hurts"]:
        drag = T["lift"]["hurts"].format(diff=st["q_diff"])
    elif st["worse"]:
        drag = MT["drag_worse"].format(more=(m["ratio"] - 1) * 100, noun=noun)
    elif not st["ni"]:
        drag = MT["drag_ni"].format(low=-st["q_low"], margin=M["margin_pts"])
    elif not st["cut"]:
        drag = MT["drag_none"].format(noun=noun)
    else:
        drag = MT["drag_low"].format(low=st["cut_low"], noun=noun)
    return score, detail, drag


def _metric_parts(ev: dict, st: dict | None) -> list[dict]:
    """The five parts on the metric. Lift is the cut; on tokens or cost, Lift takes Cost's
    weight and Cost isn't scored (`folds_cost`). With `st` None (nothing to score), Lift is
    shown as not measured."""
    m = ev["metric"]
    folds = m["id"] in M["folds_cost"]
    parts = []
    for pid in ORDER:
        weight = float(P[pid]["weight"])
        folded = False
        if pid == "lift":
            score, detail, drag = _metric_lift(st) if st else (None, M["names"][m["id"]], None)
            if folds:
                weight += float(P["cost"]["weight"])
        elif pid == "cost" and folds:
            score, detail, drag = None, MT["cost_folded"].format(name=M["names"][m["id"]]), None
            weight, folded = 0.0, True
        else:
            score, detail, drag = PARTS[pid](ev)
        parts.append(
            {
                "id": pid,
                "name": P[pid]["name"],
                "weight": round(weight, 4),
                "score": None if score is None else round(score, 1),
                "detail": detail,
                "_raw": score,
                "_drag": drag,
            }
            | ({"folded": True} if folded else {})
        )
    return parts


def _score_metric(ev: dict) -> dict[str, Any]:
    T, MT = words(ev).t, words(ev).mt
    kind = ev.get("kind")
    pairs = int(ev.get("n_pairs") or 0)
    ld = _ledger_of(ev)
    valid = ev.get("validity") or {}
    m = ev["metric"]
    if valid.get("status", "valid") != "valid":
        why = ". ".join(x.rstrip(".") for x in (valid.get("badge"), valid.get("reason")) if x)
        why = why + "." if why else why
        return _no_score(
            R["not_evidence"],
            why or R["not_evidence"]["label"],
            pairs,
            _metric_parts(ev, None),
            ld,
            kind,
        )
    if pairs == 0 or ev.get("ci_low") is None or not m.get("n"):
        return _no_score(R["none"], R["none"]["reason"], pairs, _metric_parts(ev, None), ld, kind)
    if m.get("missing"):
        return _no_score(R["none"], _missing(m, kind), pairs, _metric_parts(ev, None), ld, kind)

    st = _metric_state(ev)
    parts = _metric_parts(ev, st)
    shown = st["cut"] and st["ni"]
    for p in parts:
        p["counted"] = p["_raw"] is not None
        if not shown and p["counted"] and p["id"] in R["credit_needs_lift"]:
            p["counted"] = False
            p["note"] = MT["no_credit"]
    measured = [p for p in parts if p["_raw"] is not None]
    total_w = sum(p["weight"] for p in measured)
    weighted = sum(p["weight"] * p["_raw"] for p in measured if p["counted"])
    raw = weighted / total_w
    for p in parts:
        p["weight_used"] = round(p["weight"] / total_w, 4) if p["_raw"] is not None else 0.0

    noun = st["noun"]
    gates = []
    capped = raw

    def gate(gid: str, cap: int, text: str) -> None:
        nonlocal capped
        capped = min(capped, cap)
        gates.append({"id": gid, "cap": cap, "text": text})

    if st["hurts"]:
        gate("hurts", G["hurts_cap"], T["gates"]["hurts"].format(cap=G["hurts_cap"]))
    if st["worse"]:
        cap = G["hurts_cap"]
        gate("metric_worse", cap, MT["gates"]["metric_worse"].format(cap=cap, noun=noun))
    if not st["ni"] and not st["hurts"]:
        cap = G["not_shown_cap"]
        gate(
            "not_noninferior",
            cap,
            MT["gates"]["not_noninferior"].format(
                cap=cap, low=st["q_low"], margin=M["margin_pts"]
            ),
        )
    if not st["cut"] and not st["worse"]:
        cap = G["not_shown_cap"]
        gate("not_cut", cap, MT["gates"]["not_cut"].format(cap=cap, noun=noun))
    provisional = pairs < G["min_pairs"]
    if provisional:
        gate(
            "provisional",
            G["provisional_cap"],
            T["gates"]["provisional"].format(
                pairs=pairs, min=G["min_pairs"], cap=G["provisional_cap"]
            ),
        )
    score = _half_up(capped)

    lost = sorted(
        (p for p in measured if p["_drag"] and p["_raw"] < 100),
        key=lambda p: -p["weight"] * (100 - p["_raw"]),
    )
    drags = [p for p in lost if p["_raw"] < R["drag_below"]][: R["max_reasons"]]
    top = lost[0] if lost else None
    lift_drag = parts[0]["_drag"] or ""

    word: dict = {}
    if st["hurts"]:
        bid, word["drag"] = "doesnt", lift_drag
    elif st["worse"]:
        bid = "doesnt"
        word["drag"] = MT["doesnt_worse"].format(more=(m["ratio"] - 1) * 100, noun=noun)
    elif st["q_diff"] <= -st["margin"]:
        bid = "doesnt"
        word["drag"] = MT["doesnt_drop"].format(diff=st["q_diff"], margin=M["margin_pts"])
    elif st["cut_high"] is not None and st["cut_high"] < M["doesnt_below_cut"] * 100:
        bid = "doesnt"
        word["drag"] = MT["cant_reach"].format(
            pts=M["doesnt_below_cut"] * 100, high=st["cut_high"]
        )
    elif not st["ni"]:
        bid, word["settle"] = "not_proven", _settle_ni(st, pairs)
    elif not st["cut"]:
        bid, word["settle"] = "not_proven", MT["settle_cut"].format(pairs=pairs)
    elif score >= _band("works")["min"]:
        bid = "works"
    elif score >= _band("works_but")["min"]:
        bid, word["noun"] = "works_but", P[top["id"]]["noun"] if top else ""
    elif provisional and capped < raw:
        bid, word["settle"] = "not_proven", T["settle_more"].format(pairs=pairs)
    else:
        bid, word["drag"] = "helps_but", top["_drag"] if top else lift_drag
    if bid == "doesnt":
        for g in gates:
            if g["id"] == "provisional":
                g["text"] = T["gates"]["provisional_doesnt"].format(
                    pairs=pairs, min=G["min_pairs"]
                )
    band = _band(bid)
    label = band["label"].format(**({"noun": "", "settle": "", "drag": ""} | word))

    reason = "; ".join(p["_drag"] for p in drags) or (
        top["_drag"] if top and bid != "works" else R["works_reason"]
    )
    if provisional and not drags and capped < raw:
        reason = R["too_few_pairs"].format(pairs=pairs, min=G["min_pairs"])
    missing = [p["name"].lower() for p in parts if p["_raw"] is None and not p.get("folded")]
    if missing and not drags:
        reason += "; " + R["unmeasured"].format(names=", ".join(missing))

    f = T["formula"]
    terms = []
    for p in measured:
        if not p["counted"]:
            terms.append(f["term_no_credit"].format(weight=p["weight"] * 100, name=p["name"]))
        elif p["id"] == "lift" and m["id"] in M["folds_cost"]:
            terms.append(
                MT["formula"]["term_folded"].format(
                    weight=p["weight"] * 100,
                    score=_n(p["_raw"]),
                    cost=P["cost"]["weight"] * 100,
                    noun=noun,
                )
            )
        else:
            terms.append(f["term"].format(weight=p["weight"] * 100, score=_n(p["_raw"])))
    text = f["sum"].format(terms=" + ".join(terms), raw=weighted)
    if total_w < 1 - 1e-9:
        text = f["rescaled"].format(
            sum=text, measured=total_w * 100, names=", ".join(missing), norm=raw
        )
    why_of = f["why"] | MT["formula"]["why"]
    for g in gates:
        g["binding"] = g["cap"] < raw
    if capped < raw:
        cap = min(g["cap"] for g in gates if g["cap"] < raw)
        why = next(g["id"] for g in gates if g["cap"] == cap)
        text += "; " + f["capped"].format(cap=cap, why=why_of[why])
    text += "; " + f["final"].format(score=score)
    for p in parts:
        p.pop("_raw"), p.pop("_drag")
    return {
        "score": score,
        "band": band["id"],
        "tone": band["tone"],
        "label": label,
        "reason": reason[0].upper() + reason[1:],
        "provisional": provisional,
        "pairs": pairs,
        "parts": parts,
        "gates": gates,
        "formula": {
            "text": text,
            "measured_weight": round(total_w, 4),
            "raw": round(raw, 2),
            "not_measured": missing,
        },
        "ledger": ld,
        "ledger_text": ledger_text(ld, ev.get("kind")),
    }


def _missing(m: dict, kind: str | None = None) -> str:
    """Why there is nothing to compare: nothing recorded, neither arm solved, or one didn't."""
    MT = words(kind).mt
    noun = M["nouns"][m["id"]]
    if m["missing"] == "unsolved" and (m.get("solved_with") or m.get("solved_without")):
        arm = "with" if not m.get("solved_with") else "without"
        arm = (MT.get("arm_words") or {}).get(arm, arm)
        return MT["unsolved_one"].format(arm=arm, noun=noun)
    return MT[m["missing"]].format(noun=noun)


def _ni_pairs(st: dict, pairs: int) -> int | None:
    """About how many pairs would put the pass rate's lower bound above -margin, if the
    difference stays where it is: the interval narrows as 1 / sqrt(pairs)."""
    half = st["q_diff"] - st["q_low"]
    gap = st["q_diff"] + st["margin"]
    if half <= 0 or gap <= 0:
        return None
    return math.ceil(pairs * (half / gap) ** 2)


def _settle_ni(st: dict, pairs: int) -> str:
    need = _ni_pairs(st, pairs)
    if need and need > pairs:
        return MT["settle_ni"].format(need=need, pairs=pairs)
    return MT["settle_ni_more"].format(pairs=pairs)


def _verdict_metric(ev: dict, rig: dict) -> dict:
    """The plain answer for a run scored on a metric. Never "helps" without a cut whose 95%
    lower bound is above 0, the pass rate shown to hold, and at least `gates.min_pairs` pairs."""
    v = ev.get("validity") or {}
    m = ev["metric"]
    q = _quality(ev)
    if v.get("status", "valid") != "valid" or q is None:
        return verdict(ev, rig)  # not evidence, or no pairs: the same answer as the pass rate
    VT, MT = words(ev).vt, words(ev).mt
    noun = VD["noun"].get(ev.get("kind") or "change", VD["noun"]["change"])
    mnoun = M["nouns"][m["id"]]
    eff = efficiency(ev)
    need = int(G["min_pairs"])

    def out(vid: str, reason: str, step: str) -> dict:
        # The metric's headline leads every reason below, so the facts stay the usual four.
        return {
            "id": vid,
            "word": VD["words"][vid],
            "tone": VD["tones"][vid],
            "reason": reason[0].upper() + reason[1:] if reason else reason,
            "next": VT["next"].format(step=step),
            "facts": _facts(ev, eff, q),
        }

    if m.get("missing"):
        if m["missing"] == "unrecorded":
            step = MT["unrecorded_next"].format(mnoun=mnoun)
        elif m.get("solved_with") or m.get("solved_without"):
            step = MT["unsolved_one_next"]
        else:
            step = VT["both_fail_next"]
        return out("cant", _missing(m, ev.get("kind")), step)
    st = _metric_state(ev)
    pairs = q["n"]
    kw = {
        "line": _headline(m, ev.get("kind")),
        "noun": noun,
        "mnoun": mnoun,
        "quality": q["say_with"],
        "quality_without": q["say_without"],
        "diff": q["diff"] * 100,
        "qlow": q["low"] * 100,
        "qhigh": q["high"] * 100,
        "low": q["low"] * 100,
        "margin": M["margin_pts"],
        "pairs": pairs,
        "min": need,
    }
    if st["hurts"]:
        return out("doesnt", MT["v_hurts"].format(**kw), MT["v_hurts_next"].format(**kw))
    if st["worse"]:
        return out("doesnt", MT["v_worse"].format(**kw), MT["v_worse_next"].format(**kw))
    if st["q_diff"] <= -st["margin"]:
        return out("doesnt", MT["v_drop"].format(**kw), MT["v_hurts_next"].format(**kw))
    if st["cut_high"] is not None and st["cut_high"] < M["doesnt_below_cut"] * 100:
        pts = M["doesnt_below_cut"] * 100
        return out(
            "doesnt", MT["v_too_small"].format(pts=pts, **kw), MT["v_too_small_next"].format(**kw)
        )
    if not st["ni"]:
        want = _ni_pairs(st, pairs)
        step = (
            VT["settle_next"].format(need=want, pairs=pairs)
            if want and want > pairs
            else VT["more_next"].format(pairs=pairs)
        )
        return out("cant", MT["v_ni"].format(worst=-st["q_low"], **kw), step)
    if not st["cut"]:
        return out("cant", MT["v_not_settled"].format(**kw), VT["more_next"].format(pairs=pairs))
    if pairs < need:
        return out("cant", MT["v_few"].format(**kw), VT["few_pairs_next"].format(more=need - pairs))
    return out("helps", MT["v_helps"].format(**kw), MT["v_helps_next"].format(**kw))


def metric_summary(ev: dict) -> dict:
    """What Results shows beside the pass rate: the metric's headline and the guard."""
    m = metric_of(ev) or {}
    q = _quality(ev)
    base = {
        "id": m.get("id"),
        "name": M["names"].get(m.get("id"), ""),
        "n": m.get("n", 0),
        "margin_pts": M["margin_pts"],
        "guard": _guard(ev, q) if q else None,
        "noninferior": bool(q) and _metric_state(ev)["ni"] if m.get("with") is not None else None,
    }
    if m.get("missing") or m.get("with") is None:
        return base | {"missing": m.get("missing"), "headline": None}
    return base | {
        "with": m["with"],
        "without": m["without"],
        "ratio": m["ratio"],
        "low": m.get("low"),
        "high": m.get("high"),
        "headline": _headline(m, ev.get("kind")),
    }


def metric_guard_low(pairs: int) -> float:
    """The pass rate's 95% lower bound, in points, on `pairs` pairs under `metric.plan`'s
    assumptions (no change in the pass rate, `disagree_each_way` of the pairs each way)."""
    plan = M["plan"]
    d = round(pairs * plan["disagree_each_way"])
    a = round(pairs * plan["pass_rate"]) - d
    rest = pairs - a - 2 * d
    return stats.paired_diff_ci(stats.PairCounts(a, d, d, rest))[1] * 100


def metric_guard_pairs() -> int:
    """About how many pairs the guard needs under `metric.plan`: the fewest whose lower bound is
    above -margin_pts."""
    margin = float(M["margin_pts"])
    return next(n for n in range(2, 10_000) if metric_guard_low(n) > -margin)


def metric_plan(
    metric: str | None,
    planned: int,
    per_pair_usd: float | None,
    extends: bool = False,
    budget: float | None = None,
) -> dict | None:
    """What a planned run on a saving metric can show, before it is paid for: the pairs the guard
    needs, whether the planned pairs reach it, and the lines Measure says. None for the pass rate.
    `extends`: "Keep going until it's decided" is on (in the Lab or on a repo's Measure), so a
    run short of the guard adds pairs toward it (judge-experiment: auto_extend), as far as
    `budget` pays."""
    if not metric or metric == M["default"]:
        return None
    t = M["plan"]["text"]
    need = metric_guard_pairs()
    usd = f" (≈ {_usd(per_pair_usd * need)})" if per_pair_usd else ""
    enough = planned >= need
    lines = [t["need"].format(noun=M["nouns"][metric], need=need, usd=usd)]
    word = _word(planned, "pair")
    grows = extends and not enough
    if enough:
        lines.append(t["enough"].format(planned=f"{planned} {word}"))
    elif grows:
        cap = skills.value("judge-experiment", "auto_extend")["metric"]["max_pairs"]
        line = t["extend"].format(planned=f"{planned} {word}", max_pairs=cap)
        if per_pair_usd and budget is not None and budget < per_pair_usd * need:
            got = int(budget // per_pair_usd)
            line += " " + t["extend_budget"].format(pairs=f"{got} {_word(got, 'pair')}", need=need)
        lines.append(line)
    else:
        low = metric_guard_low(planned) if planned >= 1 else -100.0
        lines.append(
            t["short"].format(
                planned=f"{planned} {word}", low=low, margin=M["margin_pts"], need=need
            )
        )
    return {
        "metric": metric,
        "need_pairs": need,
        "planned_pairs": planned,
        "enough": enough,
        "extends": grows,
        "need_usd": round(per_pair_usd * need, 2) if per_pair_usd else None,
        "lines": lines,
    }


def _rehead(text: str, old: str, new: str) -> str:
    """`text` with a leading `old` (in any case) put in `new`'s words."""
    return new + text[len(old):] if old and text.casefold().startswith(old.casefold()) else text


def relabel(rig: dict) -> dict:
    """A Rig score kept from an earlier run, in today's words: its numbers as recorded, and its
    part names, verdict word, metric name and band head from the current rules, so a run
    recorded before a wording change reads like the rest of the app."""
    out = dict(rig)
    out["parts"] = [p | {"name": P[p["id"]]["name"]} if p.get("id") in P else p for p in rig.get("parts") or []]
    v = rig.get("verdict")
    if v and v.get("id") in VD["words"]:
        out["verdict"] = v | {"word": VD["words"][v["id"]]}
    m = rig.get("metric")
    if m and m.get("id") in M["names"]:
        old, name = m.get("name") or "", M["names"][m["id"]]
        out["metric"] = m | {"name": name, "headline": _rehead(m.get("headline") or "", old, name)}
        if out.get("verdict"):  # its reason and facts open with the metric's name too
            v = out["verdict"]
            out["verdict"] = v | {
                "reason": _rehead(v.get("reason") or "", old, name),
                "facts": [_rehead(f, old, name) for f in v.get("facts") or []],
            }
    if rig.get("band") and rig.get("label"):
        head = _band(rig["band"])["label"].split("{")[0]
        out["label"] = _rehead(rig["label"], head, head)
    return out
