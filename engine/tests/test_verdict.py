"""The plain verdict on every result: Helps / Doesn't Help / Can't Tell Yet, its reason, its
next step, and the ceiling cases where only cost, time and reliability can differ."""

from proving_ground import priors, skills, validity
from proving_ground.models import ScenarioKind
from proving_ground.rig_score import arms, efficiency, evidence_from_row, ledger, rig_score
from proving_ground.stats import summarize
from proving_ground.trial import TrialOutcome

V = skills.load("rig-score").values
VD = V["verdict"]


def tr(sid, arm, outcome, cost, secs, rep=0, detail=None):
    return TrialOutcome(
        sid, ScenarioKind.TYPICAL, arm, rep, outcome, cost_usd=cost, duration_s=secs, detail=detail
    )


def row(trials, broken=None, items=None, kind_row=None):
    """A Lab results row as app.lab_rows builds it, from trials alone."""
    s = summarize(trials)
    h = s.headline
    r = {
        "n_pairs": h.n_pairs if h else 0,
        "diff": h.diff if h else None,
        "ci_low": h.ci_low if h else None,
        "ci_high": h.ci_high if h else None,
        "verdict": s.verdict.value,
        "pass_with": h.pass_with if h else None,
        "pass_without": h.pass_without if h else None,
        "validity": validity.judge(trials, None, None, broken),
        "ledger": ledger(trials),
        "costs": priors.cost_per_solved(trials, lambda t: t.cost_usd),
        "arms": arms(trials),
    }
    if items is not None:
        r["items"] = items
    return r | (kind_row or {})


def judged(trials, **kw):
    return rig_score(evidence_from_row(row(trials, **kw), "workflow"))


TIMEOUT = "timed out after 600 s"


def finance():
    """The real finance run: the agent alone passes 5 of 5 at ~$0.04; the workflow passes 2,
    and 3 trials hit the 600 s limit."""
    ids = ["bank-recon", "pay-pressure", "q4-batch", "three-way-match", "tolerance-edges"]
    out = [tr(i, "without", "pass", 0.04, 40) for i in ids]
    out += [tr(ids[0], "with", "pass", 0.40, 208), tr(ids[1], "with", "pass", 0.34, 200)]
    out += [
        tr(i, "with", "fail", c, 621, detail=TIMEOUT)
        for i, c in zip(ids[2:], (1.14, 1.28, 1.2), strict=True)
    ]
    return out


def test_finance_is_doesnt_help_naming_the_cost_and_the_timeouts():
    rig = judged(finance())
    v = rig["verdict"]
    assert (v["id"], v["word"], v["tone"]) == ("doesnt", "Doesn't Help", "negative")
    assert v["reason"].startswith("The agent alone already passes every task; with the workflow it")
    assert "22× more per trial" in v["reason"]
    assert "timed out on 3 of 5" in v["reason"]
    assert v["next"] == "Next: a harder bench, or drop the workflow."
    # Four facts: quality, cost (per trial and per task solved), time, reliability.
    q, c, t, rel = v["facts"]
    assert q.startswith("Quality: 2 of 5 passed with, 5 of 5 passed without")
    assert "$0.87 vs $0.040 per trial (22×)" in c and "per task solved" in c
    assert t.startswith("Time: 7.6 min vs 40 s per trial (11×)")
    assert rel == "Reliability: with, 3 of 5 timed out; without, all 5 ran cleanly"
    # The card agrees: a score in the "doesn't work" band, and timeouts cost Reliable.
    assert rig["band"] == "doesnt" and rig["score"] is not None
    reliable = next(p for p in rig["parts"] if p["id"] == "reliable")
    assert reliable["detail"].startswith("7 of 10 trials ran cleanly")
    assert "3 timed out" in rig["ledger_text"]
    # Five pairs cap how high it can go, not this answer: the gate says so, not "at most not proven".
    gate = next(g for g in rig["gates"] if g["id"] == "provisional")
    assert gate["text"] == (
        "Provisional: 5 pairs, under 10 — enough to show it doesn't help, not enough to show it helps."
    )


def ceiling(cost_with, secs_with, n=5, cost_wo=0.04, secs_wo=40):
    ids = [f"t{i}" for i in range(n)]
    out = [tr(i, "without", "pass", cost_wo, secs_wo) for i in ids]
    out += [
        tr(i, "with", "pass", cost_with * (1 + k / 50), secs_with * (1 + k / 50))
        for k, i in enumerate(ids)
    ]
    return out


def test_both_always_pass_and_far_dearer_is_doesnt_help_with_a_score():
    rig = judged(ceiling(1.0, 300))
    v = rig["verdict"]
    assert v["id"] == "doesnt"
    assert v["reason"].startswith(
        "Both pass every task, so quality is the same; with the workflow it costs"
    )
    assert v["next"].startswith("Next: drop the workflow")
    assert rig["band"] == "doesnt" and rig["score"] is not None
    assert rig["score"] <= V["gates"]["ceiling_worse_cap"]
    assert "same pass rate" in rig["label"]
    lift = next(p for p in rig["parts"] if p["id"] == "lift")
    assert lift["score"] is None and "can't differ" in lift["detail"]


def test_both_always_pass_and_clearly_cheaper_is_helps_on_enough_pairs():
    rig = judged(ceiling(0.01, 15, n=12))
    v = rig["verdict"]
    assert v["id"] == "helps", v
    assert v["reason"].startswith("Both pass every task; with the workflow it costs")
    assert "less per trial" in v["reason"] and "faster" in v["reason"]
    assert rig["score"] is not None and rig["band"] in ("works", "works_but", "helps_but")


def test_cheaper_at_the_ceiling_on_few_pairs_is_cant_tell_yet():
    v = judged(ceiling(0.01, 15, n=5))["verdict"]
    assert v["id"] == "cant" and "on 5 pairs; 10 are needed" in v["reason"]
    assert v["next"] == "Next: run 5 more pairs."


def test_ceiling_with_no_clear_difference_is_cant_tell_yet_and_no_score():
    rig = judged(ceiling(0.042, 41))
    assert rig["verdict"]["id"] == "cant" and rig["score"] is None
    assert "don't clearly differ" in rig["verdict"]["reason"]


def test_a_big_ratio_that_isnt_consistent_is_not_clear():
    """1.5× on average but one task far cheaper: the interval reaches 1, so not clearly."""
    ids = ["a", "b", "c"]
    t = [tr(i, "without", "pass", 0.1, 40) for i in ids]
    t += [
        tr("a", "with", "pass", 0.6, 40),
        tr("b", "with", "pass", 0.6, 40),
        tr("c", "with", "pass", 0.02, 40),
    ]
    eff = efficiency(evidence_from_row(row(t)))
    assert eff["cost"]["clearly"] is None and eff["call"] is None


def test_both_always_fail_is_cant_tell_yet():
    t = [tr(i, a, "fail", 0.1, 50) for i in "abcde" for a in ("with", "without")]
    rig = judged(t)
    v = rig["verdict"]
    assert v["id"] == "cant" and rig["score"] is None
    assert "too hard or the check may be wrong" in v["reason"]


def test_a_broken_check_is_cant_tell_yet_with_the_fix():
    t = [tr(i, a, "fail", 0.1, 50) for i in "abc" for a in ("with", "without")]
    rig = judged(t, broken={"audit": "`write the docs` isn't a command"})
    v = rig["verdict"]
    assert (v["id"], v["word"]) == ("cant", "Can't Tell Yet")
    assert v["reason"] == "The task's check isn't a command, so every trial fails both ways."
    assert v["next"] == "Next: give the task a real check."
    assert rig["score"] is None and rig["band"] == "not_evidence"


def test_a_real_lift_is_helps():
    t = []
    for i in range(20):
        t.append(tr(f"t{i}", "with", "pass", 0.12, 60))
        t.append(tr(f"t{i}", "without", "pass" if i < 6 else "fail", 0.1, 50))
    rig = judged(t)
    v = rig["verdict"]
    assert v["id"] == "helps", v
    assert v["reason"].startswith(
        "20 of 20 passed with vs 6 of 20 passed without (+70 pts, 95% interval"
    )
    assert v["next"].startswith("Next: use it")
    assert rig["band"] in ("works", "works_but", "helps_but")


def test_a_lift_on_too_few_pairs_says_how_many_more():
    t = []
    for i in range(6):
        t.append(tr(f"t{i}", "with", "pass", 0.1, 50))
        t.append(tr(f"t{i}", "without", "fail", 0.1, 50))
    v = judged(t)["verdict"]
    assert v["id"] == "cant" and "on 6 pairs; 10 are needed" in v["reason"]
    assert v["next"] == "Next: run 4 more pairs."


def test_an_unsettled_result_says_how_many_pairs_would_settle_it():
    t = []
    for i in range(6):
        t.append(tr(f"t{i}", "with", "pass" if i < 4 else "fail", 0.1, 50))
        t.append(tr(f"t{i}", "without", "pass" if i < 3 else "fail", 0.1, 50))
    v = judged(t)["verdict"]
    assert v["id"] == "cant" and "not settled" in v["reason"]
    assert v["next"].startswith("Next: run about ") and "(6 so far)" in v["next"]


def test_no_pairs_is_cant_tell_yet():
    v = rig_score(evidence_from_row({"n_pairs": 0}))["verdict"]
    assert v["id"] == "cant" and v["reason"] == "No complete pairs yet."


# ---------- partial credit (items) is preferred when the row has it ----------


def itr(sid, arm, outcome, right, total, cost=0.1, secs=50):
    return TrialOutcome(
        sid, ScenarioKind.TYPICAL, arm, 0, outcome, cost_usd=cost, duration_s=secs,
        items_right=right, items_total=total,
    )  # fmt: skip


def irow(trials):
    """A results row as the engine builds it, with the summary's own `items`."""
    s = summarize(trials)
    return row(trials, items=s.items.as_json() if s.items else None)


def ijudged(trials):
    return rig_score(evidence_from_row(irow(trials), "workflow"))


def test_a_pass_rate_tie_with_an_item_lift_is_scored_and_helps_on_items():
    """Every trial fails its all-or-nothing check both ways, but with the workflow the agent
    gets 11 of 12 invoices right against 6 of 12: judged on items, not "both always fail"."""
    t = []
    for i in range(12):
        t.append(itr(f"t{i}", "with", "fail", 11, 12))
        t.append(itr(f"t{i}", "without", "fail", 6 + (i % 2), 12))
    r = irow(t)
    assert r["validity"]["cause"] == "both_fail" and r["items"]["n"] == 12
    rig = rig_score(evidence_from_row(r, "workflow"))
    assert rig["quality"] == "items"
    assert rig["score"] is not None and rig["band"] != "not_evidence"
    lift = next(p for p in rig["parts"] if p["id"] == "lift")
    assert lift["score"] == 100 and "pts of items right" in lift["detail"]
    v = rig["verdict"]
    assert v["id"] == "helps", v
    assert v["reason"].startswith("132 of 144 items right with vs 78 of 144 without (+37 pts")
    assert v["facts"][0].startswith("Quality: 132 of 144 items right with, 78 of 144 without")


def test_a_pass_rate_tie_with_items_worse_is_doesnt_help_on_items():
    t = []
    for i in range(12):
        t.append(itr(f"t{i}", "with", "fail", 5 + (i % 2), 12))
        t.append(itr(f"t{i}", "without", "fail", 11, 12))
    rig = ijudged(t)
    assert rig["band"] == "doesnt" and rig["score"] is not None
    v = rig["verdict"]
    assert v["id"] == "doesnt" and v["reason"].startswith(
        "It does worse: 66 of 144 items right with"
    )


def test_items_at_the_ceiling_fall_to_the_cost_and_time_rule():
    t = []
    for i in range(5):
        t.append(itr(f"t{i}", "with", "pass", 12, 12, cost=1.0 + i / 50, secs=300))
        t.append(itr(f"t{i}", "without", "pass", 12, 12, cost=0.04, secs=40))
    rig = ijudged(t)
    assert rig["quality"] == "items" and rig["band"] == "doesnt"
    assert rig["score"] is not None and rig["score"] <= V["gates"]["ceiling_worse_cap"]
    assert rig["verdict"]["reason"].startswith("Both pass every task, so quality is the same")


def test_items_at_the_floor_stay_cant_tell_yet():
    t = [itr(f"t{i}", a, "fail", 0, 12) for i in range(5) for a in ("with", "without")]
    rig = ijudged(t)
    assert rig["score"] is None and rig["verdict"]["id"] == "cant"
    assert "too hard or the check may be wrong" in rig["verdict"]["reason"]


def test_the_agent_alone_getting_every_item_right_is_doesnt_help():
    t = []
    for i in range(6):
        t.append(itr(f"t{i}", "with", "fail" if i < 3 else "pass", 10 if i < 3 else 12, 12))
        t.append(itr(f"t{i}", "without", "pass", 12, 12))
    v = ijudged(t)["verdict"]
    assert v["id"] == "doesnt"
    assert v["reason"].startswith(
        "The agent alone already gets every item right; with the workflow it gets 66 of 72 items right"
    )


def test_without_items_the_pass_rate_is_the_quality():
    t = []
    for i in range(12):
        t.append(tr(f"t{i}", "with", "pass", 0.1, 50))
        t.append(tr(f"t{i}", "without", "pass", 0.1, 50))
    rig = judged(t)
    assert rig["quality"] == "pass_rate" and rig["verdict"]["id"] == "cant"


def test_same_evidence_same_verdict():
    a, b = judged(finance()), judged(finance())
    assert a["verdict"] == b["verdict"]


def test_ceiling_results_still_dont_feed_learned_priors():
    """Cost isn't quality: a both-always-pass result stays uninformative for priors."""
    r = row(ceiling(1.0, 300))
    assert r["validity"]["status"] == "uninformative" and r["validity"]["cause"] == "both_pass"


def test_every_verdict_word_comes_from_the_skill():
    words = {judged(finance())["verdict"]["word"], judged(ceiling(0.042, 41))["verdict"]["word"]}
    assert words <= set(VD["words"].values())


def test_arms_price_a_reused_baseline_trial_at_what_it_cost_when_it_ran():
    from dataclasses import replace

    t = [
        tr("a", "with", "pass", 0.5, 100),
        replace(tr("a", "without", "pass", 0.0, 40), reused_from=7),
    ]
    a = arms(t, lambda x: 0.05)  # only the reused trial is priced by its source
    assert (a["with"]["cost_usd"], a["without"]["cost_usd"]) == (0.5, 0.05)
    assert a["tasks"] == [{"id": "a", "cost": [0.5, 0.05], "duration": [100.0, 40.0]}]


def test_a_pooled_suite_adds_up_each_benchs_arms():
    from proving_ground.rig_score import pool_evidence

    a, b = row(finance()) | {"bench": "finance"}, row(ceiling(1.0, 300)) | {"bench": "bugfix"}
    ev = pool_evidence([a, b], {"n_pairs": 10, "diff": -0.3, "ci_low": -0.5, "ci_high": -0.1})
    w = ev["arms"]["with"]
    assert (w["trials"], w["timed_out"], len(ev["arms"]["tasks"])) == (10, 3, 10)
    assert ev["arms"]["tasks"][0]["id"].startswith("finance/")
    assert rig_score(ev)["verdict"]["id"] == "cant"  # the pool holds a result that isn't evidence
