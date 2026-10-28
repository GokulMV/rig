"""The Rig score on a metric (tokens, cost or time per solved task): the bootstrap, the
non-inferiority guard, the folded Cost part, the gates, bands, reason lines and the verdict.
And the pass rate itself, unchanged."""

import copy
import math

import pytest

from proving_ground import skills, stats
from proving_ground.models import ScenarioKind
from proving_ground.rig_score import (
    evidence_from_row,
    followed,
    metric_evidence,
    rig_score,
)
from proving_ground.trial import TrialOutcome

V = skills.load("rig-score").values
M = V["metric"]


def part(out, pid):
    return next(p for p in out["parts"] if p["id"] == pid)


def gate_ids(out):
    return [g["id"] for g in out["gates"]]


# ---------- the bootstrap ----------


def test_the_ratio_is_per_solved_task_and_the_interval_is_seeded():
    pairs = [(10.0, 1, 20.0, 1), (12.0, 1, 18.0, 1), (8.0, 0, 22.0, 1), (11.0, 1, 21.0, 0)]
    ratio, lo, hi = stats.paired_ratio_ci(pairs, 2000, 0)
    # with: 41 tokens over 3 solved; without: 81 over 3 solved
    assert ratio == pytest.approx((41 / 3) / (81 / 3))
    assert lo < ratio < hi
    assert stats.paired_ratio_ci(pairs, 2000, 0) == (ratio, lo, hi)  # same trials, same interval
    assert stats.paired_ratio_ci(pairs, 2000, 1) != (ratio, lo, hi)  # the seed is what fixes it


def test_a_resample_that_solved_nothing_counts_against_the_change():
    # One pair in three solved anything on "with": many resamples have no "with" figure.
    pairs = [(5.0, 1, 10.0, 1), (5.0, 0, 10.0, 1), (5.0, 0, 10.0, 1)]
    _, lo, hi = stats.paired_ratio_ci(pairs, 500, 0)
    assert math.isinf(hi) and lo < 1


def test_under_min_pairs_there_is_no_interval_and_nothing_solved_raises():
    assert stats.paired_ratio_ci([(5.0, 1, 10.0, 1)], 100, 0, 2) == (0.5, None, None)
    with pytest.raises(ValueError):
        stats.paired_ratio_ci([(5.0, 0, 10.0, 1), (5.0, 0, 9.0, 1)], 100, 0)


# ---------- the metric's evidence from trials ----------


def trial(sid, arm, outcome, tokens=1000, cost=0.1, secs=60.0, rep=0, kind="typical", **kw):
    return TrialOutcome(
        sid, ScenarioKind(kind), arm, rep, outcome, tokens, 0, cost, secs, **kw
    )


def test_tokens_per_solved_task_over_the_complete_pairs():
    trials = [
        trial("a", "with", "pass", 1_000),
        trial("a", "without", "pass", 3_000),
        trial("b", "with", "fail", 500),  # a fail spent its tokens too
        trial("b", "without", "pass", 2_000),
        trial("c", "with", "pass", 9_999),  # no "without": not a complete pair
        trial("d", "with", "pass", 100, kind="imaginary"),
        trial("d", "without", "fail", 100, kind="imaginary"),
    ]
    m = metric_evidence(trials, "tokens")
    assert m["n"] == 2 and m["solved_with"] == 1 and m["solved_without"] == 2
    assert m["with"] == 1_500 and m["without"] == 2_500
    assert m["ratio"] == pytest.approx(0.6)


def test_cost_counts_a_reused_trial_at_what_it_cost_when_it_ran():
    trials = [
        trial("a", "with", "pass", cost=0.1),
        trial("a", "without", "pass", cost=0.0, reused_from=7),
        trial("b", "with", "pass", cost=0.1),
        trial("b", "without", "pass", cost=0.0, reused_from=7),
    ]
    m = metric_evidence(trials, "cost", cost_of=lambda t: 0.4)
    assert m["without"] == pytest.approx(0.4) and m["ratio"] == pytest.approx(0.25)


def test_nothing_to_compare_says_why():
    assert metric_evidence([], "pass_rate") is None
    assert metric_evidence([], None) is None
    with pytest.raises(ValueError, match="unknown metric"):
        metric_evidence([], "vibes")
    unsolved = [trial("a", "with", "fail"), trial("a", "without", "pass")]
    got = metric_evidence(unsolved, "tokens")
    assert got["missing"] == "unsolved" and (got["solved_with"], got["solved_without"]) == (0, 1)
    unpriced = [trial("a", "with", "pass", cost=0.0), trial("a", "without", "pass", cost=0.0)]
    assert metric_evidence(unpriced, "cost")["missing"] == "unrecorded"
    assert metric_evidence([], "time") == {"id": "time", "n": 0}


# ---------- the score on a metric ----------


def ev(**kw):
    """A skill that halves tokens at the same pass rate, on 40 pairs that mostly agree."""
    base = {
        "kind": "skill",
        "n_pairs": 40,
        "diff": 0.0,
        "ci_low": -0.07,
        "ci_high": 0.07,
        "verdict": "inconclusive",
        "pass_with": 0.8,
        "pass_without": 0.8,
        "costs": {
            "with": {"spent_usd": 2.0, "solved": 32, "tasks": 40},
            "without": {"spent_usd": 4.0, "solved": 32, "tasks": 40},
        },
        "local": False,
        "opened": {"read": 40, "opened": 40},
        "holds_up": None,
        "ledger": {
            "total": 80, "with": 40, "without": 40, "pairs": 40, "logs_read": 40,
            "clean": 80, "timed_out": 0, "errored": 0, "broken": 0,
        },
        "judge": None,
        "metric": {
            "id": "tokens", "n": 40, "with": 21_400.0, "without": 44_100.0,
            "ratio": 21_400 / 44_100, "low": 0.42, "high": 0.55,
            "solved_with": 32, "solved_without": 32,
        },
    }  # fmt: skip
    return base | kw


def metric(**kw):
    return ev()["metric"] | kw


def test_a_halving_at_the_same_pass_rate_works():
    out = rig_score(ev())
    lift = part(out, "lift")
    # Lift on the cut's lower bound: 1 - 0.55 = 45% of the 50% target.
    assert lift["score"] == pytest.approx(90.0)
    assert lift["weight"] == pytest.approx(0.6)  # it took Cost's 20%
    assert lift["detail"] == (
        "the cut in tokens per solved task is at least 45% (target 50%)"
    )
    cost = part(out, "cost")
    assert cost["score"] is None and cost["folded"] and cost["weight"] == 0
    assert cost["detail"] == "in Lift: Tokens per Solved Task is what is measured"
    # 60% × 90 + 15% × 100 + 10% × 100 over 85% (holds up not measured)
    assert out["score"] == round((0.6 * 90 + 0.15 * 100 + 0.10 * 100) / 0.85)
    assert out["band"] == "works" and out["label"] == "Works — use it"
    assert out["gates"] == []
    assert "Lift takes Cost's 20%: the measure is tokens" in out["formula"]["text"]
    assert out["formula"]["not_measured"] == ["holds up"]  # cost isn't "not measured"
    assert out["verdict"]["id"] == "helps"
    assert out["metric"]["headline"] == (
        "Tokens per Solved Task: with 21.4k vs without 44.1k (-51%, 95% interval -58% to -45%)"
    )
    assert out["verdict"]["reason"].startswith(out["metric"]["headline"] + ", and the pass rate")
    # The headline isn't repeated as a fact: quality (and, with `arms`, cost, time, reliability).
    assert [f.split(":")[0] for f in out["verdict"]["facts"]] == ["Quality"]
    assert out["metric"]["guard"] == (
        "Pass rate: 32 of 40 passed with vs 32 of 40 passed without (+0 pts; at worst -7 pts,"
        " within the 10-pt margin)"
    )
    assert out["metric"]["noninferior"] is True


def test_time_keeps_cost_as_its_own_part():
    out = rig_score(ev(metric=metric(id="time")))
    assert part(out, "lift")["weight"] == pytest.approx(0.4)
    cost = part(out, "cost")
    assert cost["score"] == 100 and not cost.get("folded")  # half the cost: full marks


def test_no_cut_claimed_until_the_pass_rate_is_shown_to_hold():
    # 20 pairs that all agree: the pass rate's interval still reaches -13 pts.
    out = rig_score(ev(n_pairs=20, ci_low=-0.13, ci_high=0.13, metric=metric(n=20)))
    lift = part(out, "lift")
    assert lift["score"] == 0
    assert lift["detail"].endswith("; counts once the pass rate is shown to hold")
    assert part(out, "reliable")["counted"] is False
    assert part(out, "reliable")["note"] == "counts once a cut is shown and the pass rate holds"
    assert "not_noninferior" in gate_ids(out) and out["score"] <= 49
    assert out["band"] == "not_proven"
    # 20 pairs × (13 / 10)² = 33.8
    assert out["label"] == (
        "Not Proven — about 34 pairs would show the pass rate holds (20 so far)"
    )
    assert out["reason"].startswith("The pass rate could be 13 pts worse (the margin is 10)")
    assert out["verdict"]["id"] == "cant"
    assert out["verdict"]["next"] == "Next: run about 34 pairs (20 so far)."
    assert out["metric"]["noninferior"] is False
    assert "past the 10-pt margin" in out["metric"]["guard"]


def test_the_margin_is_strict():
    at = rig_score(ev(ci_low=-0.10))
    assert "not_noninferior" in gate_ids(at)
    assert "not_noninferior" not in gate_ids(rig_score(ev(ci_low=-0.099)))


def test_it_does_worse_on_the_pass_rate():
    out = rig_score(ev(diff=-0.3, ci_low=-0.5, ci_high=-0.1, verdict="hurts", pass_with=0.5))
    assert gate_ids(out) == ["hurts"] and out["score"] <= 20
    assert out["band"] == "doesnt"
    assert out["label"] == "Doesn't Work — does worse than the plain agent (-30 pts)"
    assert out["verdict"]["id"] == "doesnt"
    assert out["verdict"]["reason"].startswith("It does worse on the pass rate: 20 of 40")


def test_the_pass_rate_drop_past_the_margin_is_doesnt_even_when_unsettled():
    out = rig_score(ev(diff=-0.12, ci_low=-0.3, ci_high=0.05))
    assert out["band"] == "doesnt"
    assert out["label"] == "Doesn't Work — the pass rate drops -12 pts, past the 10-pt margin"
    assert out["verdict"]["id"] == "doesnt"


def test_it_uses_more():
    out = rig_score(ev(metric=metric(ratio=1.4, low=1.2, high=1.6)))
    assert "metric_worse" in gate_ids(out) and out["score"] <= 20
    assert "not_cut" not in gate_ids(out)
    assert out["label"] == "Doesn't Work — it uses 40% more tokens per solved task"
    assert out["verdict"]["id"] == "doesnt"


def test_a_cut_that_cannot_matter():
    out = rig_score(ev(metric=metric(ratio=0.99, low=0.97, high=1.02)))
    assert out["band"] == "doesnt"
    assert out["label"] == "Doesn't Work — the cut can't reach 5% (at best 3%)"
    assert "not_cut" in gate_ids(out)


def test_a_cut_not_settled():
    out = rig_score(ev(metric=metric(ratio=0.85, low=0.7, high=1.05)))
    assert out["band"] == "not_proven"
    assert out["label"] == "Not Proven — more pairs would settle the cut (40 so far)"
    assert part(out, "lift")["detail"] == (
        "no cut in tokens per solved task shown (the interval reaches +5%)"
    )
    assert out["verdict"]["id"] == "cant"


def test_an_unbounded_interval_is_no_cut():
    out = rig_score(ev(metric=metric(low=0.4, high=None)))
    assert part(out, "lift")["score"] == 0
    assert "no upper end" in out["metric"]["headline"]
    assert out["band"] == "not_proven"


def test_one_pair_has_no_interval():
    out = rig_score(ev(n_pairs=1, metric=metric(n=1, low=None, high=None)))
    assert part(out, "lift")["score"] == 0
    assert out["metric"]["headline"].endswith("(-51%; an interval needs 2 pairs)")
    assert "provisional" in gate_ids(out) and out["verdict"]["id"] != "helps"


def test_few_pairs_is_provisional_and_never_helps():
    out = rig_score(
        ev(n_pairs=8, ci_low=-0.05, ledger=ev()["ledger"] | {"pairs": 8}, metric=metric(n=8))
    )
    assert out["provisional"] and out["score"] <= 59
    assert out["verdict"]["id"] == "cant"
    assert "on 8 pairs; 10 are needed" in out["verdict"]["reason"]


def test_both_always_pass_is_evidence_for_a_metric():
    both = {"status": "uninformative", "cause": "both_pass", "badge": "Uninformative: both always pass"}
    out = rig_score(ev(validity=both, pass_with=1.0, pass_without=1.0, ci_low=-0.05))
    assert out["score"] is not None and out["band"] == "works"
    # ...and still not evidence on the pass rate (no clear cost or time difference recorded)
    assert rig_score(ev(validity=both, metric=None))["band"] == "not_evidence"


def test_invalid_is_still_not_evidence():
    bad = {"status": "invalid", "cause": "broken_check", "badge": "Invalid: the check is broken"}
    out = rig_score(ev(validity=bad))
    assert out["score"] is None and out["band"] == "not_evidence"
    assert out["verdict"]["id"] == "cant"


def test_nothing_solved_is_no_score():
    out = rig_score(ev(metric={"id": "tokens", "n": 40, "missing": "unsolved"}))
    assert out["score"] is None and out["band"] == "none"
    assert out["reason"] == (
        "Neither arm solved a task, so tokens per solved task can't be compared."
    )
    assert out["metric"]["headline"] is None
    one = {"id": "tokens", "n": 3, "missing": "unsolved", "solved_with": 2, "solved_without": 0}
    out = rig_score(ev(metric=one))
    assert out["reason"] == (
        'The "without" arm solved no task, so tokens per solved task can\'t be compared.'
    )
    assert out["verdict"]["next"] == "Next: run more pairs, or score it on the pass rate."
    priced = rig_score(ev(metric={"id": "cost", "n": 40, "missing": "unrecorded"}))
    assert priced["verdict"]["next"].startswith("Next: a run whose trials record cost")


def test_the_baseline_ceiling_rule_is_the_guards_job_here():
    # The plain agent passes everything and the change misses one: the guard decides.
    out = rig_score(ev(pass_without=1.0, pass_with=0.975, diff=-0.025, ci_low=-0.09))
    assert out["band"] == "works"


def test_same_evidence_same_score():
    e = ev()
    assert rig_score(copy.deepcopy(e)) == rig_score(copy.deepcopy(e))


# ---------- the pass rate, unchanged ----------


def pass_rate_ev():
    e = ev()
    e.pop("metric")
    return e | {"diff": 0.3, "ci_low": 0.12, "ci_high": 0.5, "verdict": "helps", "pass_with": 1.0}


@pytest.mark.parametrize("m", [None, {"id": "pass_rate"}, {}])
def test_the_pass_rate_metric_is_the_score_as_it_was(m):
    plain = rig_score(pass_rate_ev())
    assert "metric" not in plain
    assert rig_score(pass_rate_ev() | {"metric": m}) == plain


def test_a_row_without_a_metric_makes_the_same_evidence():
    row = {"n_pairs": 3, "diff": 0.1, "ci_low": -0.2, "ci_high": 0.4}
    assert "metric" not in evidence_from_row(row, "skill")
    assert evidence_from_row(row | {"metric": metric()}, "skill")["metric"] == metric()


# ---------- Followed, for each kind of change ----------


def test_followed_for_hooks_instructions_and_mcp_servers():
    hook = followed({"kind": "hook", "opened": None})
    assert hook == (
        None, "a hook runs by itself, so there is nothing for the agent to follow or skip", None
    )
    ins = followed({"kind": "instructions"})
    assert ins[0] is None and "isn't read from the logs" in ins[1]
    mcp = followed({"kind": "mcp", "opened": {"read": 4, "opened": 3}})
    assert mcp[0] == 75
    assert mcp[1] == 'called the MCP server in 3 of the 4 "with" trials whose logs could be read'
    assert mcp[2] == (
        'the agent didn\'t call the MCP server in 1 of the 4 "with" trials whose logs could be read'
    )
    assert followed({"kind": "mcp", "opened": None})[1] == "no session logs to read"
    hurt = {"diff": -0.3, "ci_low": -0.5, "ci_high": -0.1, "verdict": "hurts", "metric": None}
    assert rig_score(ev(kind="hook", **hurt))["verdict"]["next"] == (
        'Next: drop the hook, or read the failing "with" trials to see what it breaks.'
    )


# ---------- which trial fields feed each metric ----------


def test_each_metric_reads_its_own_fields_and_tokens_are_in_plus_out():
    """Tokens: tokens_in + tokens_out as Harbor records them (its input count includes cached
    input). Cost: cost_usd. Time: duration_s. Nothing else."""

    def t(arm, tin, tout, cost, secs):
        return TrialOutcome("a", ScenarioKind.TYPICAL, arm, 0, "pass", tin, tout, cost, secs)

    trials = [t("with", 700, 300, 0.5, 30.0), t("without", 3_000, 1_000, 2.0, 90.0)]
    assert metric_evidence(trials, "tokens")["with"] == 1_000
    assert metric_evidence(trials, "tokens")["without"] == 4_000
    assert metric_evidence(trials, "cost")["with"] == 0.5
    assert metric_evidence(trials, "time")["without"] == 90.0
    assert "cached input included" in M["describe"]["tokens"]


# ---------- sizing before a run ----------


def test_the_guard_needs_about_39_pairs_under_the_plans_assumptions():
    from proving_ground.rig_score import metric_guard_low, metric_guard_pairs

    need = metric_guard_pairs()
    assert need == 39
    assert metric_guard_low(need) > -M["margin_pts"] >= metric_guard_low(need - 1)


def test_a_pilot_is_told_it_cannot_be_credited_a_saving():
    from proving_ground.rig_score import metric_plan

    assert metric_plan("pass_rate", 3, 0.7) is None
    pilot = metric_plan("tokens", 3, 0.72)
    assert not pilot["enough"] and pilot["need_pairs"] == 39 and pilot["need_usd"] == 28.08
    assert pilot["lines"][0].startswith(
        "Scored on tokens, the pass-rate guard needs about 39 pairs (≈ $28.08)"
    )
    assert pilot["lines"][1].startswith("This run plans 3 pairs: at best the pass rate's interval")
    assert "no saving can be credited" in pilot["lines"][1]
    # Shown together, the pairs needed are said once: in the first line, not again in the second.
    assert "39" not in pilot["lines"][1]
    full = metric_plan("cost", 42, None)
    assert full["enough"] and full["need_usd"] is None
    assert full["lines"][1] == "This run plans 42 pairs: enough for the guard if the pass rate holds."
