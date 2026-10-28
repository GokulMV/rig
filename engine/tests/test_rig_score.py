"""The Rig score: every part, every gate, the bands, missing parts, and a real run's numbers."""

import copy
import math

import pytest

from proving_ground import skills
from proving_ground.rig_score import (
    cost,
    evidence_from_row,
    followed,
    holds_up,
    holds_up_verdict,
    lift,
    pool_evidence,
    reliable,
    rig_score,
)

V = skills.load("rig-score").values
P = V["parts"]


def ev(**kw):
    """A rig that works on every part: clear lift, same cost, followed, generalises, clean."""
    base = {
        "kind": "workflow",
        "n_pairs": 30,
        "diff": 0.5,
        "ci_low": 0.3,
        "ci_high": 0.7,
        "verdict": "helps",
        "costs": {
            "with": {"spent_usd": 3.0, "solved": 30, "tasks": 30},
            "without": {"spent_usd": 3.0, "solved": 15, "tasks": 30},
        },
        "local": False,
        "adherence": {"read": 30, "steps_run": 1.0, "models_ok": 1.0, "steps": 4},
        "opened": None,
        "holds_up": "generalises",
        "trials": {"total": 60, "errored": 0, "broken": 0},
        "judge": None,
    }
    return base | kw


def part(out, pid):
    return next(p for p in out["parts"] if p["id"] == pid)


def test_the_skill_is_registered_and_its_weights_add_up():
    assert "rig-score" in skills.NAMES
    assert math.isclose(sum(p["weight"] for p in P.values()), 1.0)
    assert [p for p in P] == ["lift", "cost", "followed", "holds_up", "reliable"]


# ---------- Lift ----------


@pytest.mark.parametrize(
    ("low", "want"), [(-0.4, 0), (0.0, 0), (0.05, 20), (0.125, 50), (0.25, 100), (0.6, 100)]
)
def test_lift_is_linear_in_the_lower_bound(low, want):
    assert lift(ev(ci_low=low))[0] == pytest.approx(want)


def test_lift_says_why_it_is_low():
    assert lift(ev(ci_low=-0.2, diff=0.0, verdict="inconclusive"))[2] == "no lift shown"
    assert lift(ev(ci_low=-0.6, ci_high=-0.1, diff=-0.3, verdict="hurts"))[2] == (
        "does worse than the plain agent (-30 pts)"
    )
    assert lift(ev(ci_low=0.05))[2] == "lift could be as small as +5 pts"


# ---------- Cost ----------


def costs(w, wo, sw=10, swo=10, tasks=10):
    return {
        "with": {"spent_usd": w, "solved": sw, "tasks": tasks},
        "without": {"spent_usd": wo, "solved": swo, "tasks": tasks},
    }


@pytest.mark.parametrize(("ratio", "want"), [(0.5, 100), (1.2, 100), (5.0, 0), (40.0, 0)])
def test_cost_ends(ratio, want):
    assert cost(ev(costs=costs(ratio, 1.0)))[0] == pytest.approx(want)


def test_cost_is_log_linear_between():
    mid = math.sqrt(P["cost"]["full"] * P["cost"]["zero"])  # halfway in log terms
    assert cost(ev(costs=costs(mid, 1.0)))[0] == pytest.approx(50)
    s2, s3 = cost(ev(costs=costs(2.0, 1.0)))[0], cost(ev(costs=costs(3.0, 1.0)))[0]
    assert 100 > s2 > s3 > 0


def test_cost_is_per_solved_task_when_both_arms_solved_some_else_per_task():
    # Same spend, but "with" solves twice as many: half the cost per solved task.
    s, detail, _ = cost(ev(costs=costs(2.0, 1.0, sw=10, swo=5)))
    assert s == 100 and detail == "1.0× the plain agent's cost per solved task"
    _, detail, _ = cost(ev(costs=costs(2.0, 1.0, sw=0, swo=5)))
    assert detail == "2.0× the plain agent's cost per task"


def test_a_local_model_costs_nothing_and_unpriced_runs_are_not_measured():
    assert cost(ev(local=True, costs=costs(0, 0)))[:2] == (100.0, "costs nothing (a local model)")
    assert cost(ev(costs=costs(0, 0)))[0] is None
    assert cost(ev(costs=None))[0] is None


# ---------- Followed ----------


def test_followed_for_a_workflow_is_steps_run_and_right_models():
    s, detail, drag = followed(
        ev(adherence={"read": 4, "steps_run": 0.5, "models_ok": 0.25, "steps": 4})
    )
    share = P["followed"]["steps_share"]
    assert s == pytest.approx(100 * (share * 0.5 + (1 - share) * 0.25))
    # Steps are averaged over the trials read, and the text says which trials those are.
    assert detail == (
        'on average 2 of 4 steps run, 1 on the right model, in the 4 "with" trials whose logs '
        "could be read"
    )
    assert drag == "the agent skipped 2 of 4 steps on average"
    _, _, drag = followed(ev(adherence={"read": 4, "steps_run": 1.0, "models_ok": 0.5, "steps": 4}))
    assert drag == "2 steps ran on the wrong model on average"


def test_followed_for_a_skill_is_whether_it_was_opened():
    s, detail, drag = followed(ev(kind="skill", adherence=None, opened={"read": 5, "opened": 2}))
    assert s == pytest.approx(40)
    assert detail == 'opened the skill in 2 of the 5 "with" trials whose logs could be read'
    assert drag == (
        'the agent didn\'t open the skill in 3 of the 5 "with" trials whose logs could be read'
    )


def test_followed_without_logs_is_not_measured():
    assert followed(ev(adherence=None))[0] is None
    assert followed(ev(adherence={"read": 0, "steps_run": None}))[0] is None
    assert followed(ev(kind="skill", opened=None))[0] is None


# ---------- Holds up ----------


@pytest.mark.parametrize(("v", "want"), [("generalises", 100), ("unclear", None), ("overfit", 0)])
def test_holds_up(v, want):
    assert holds_up(ev(holds_up=v))[0] == want


@pytest.mark.parametrize(
    ("why", "words"),
    [
        ("no_pairs", "No held-out tasks ran, so it's unknown whether this holds on unseen tasks"),
        (
            "no_gain",
            "No gain on the visible tasks, so there's nothing for held-out tasks to confirm",
        ),
        (None, "Held-out tasks neither confirm nor contradict the gain on the visible ones"),
    ],
)
def test_unclear_is_not_measured_and_says_why_in_words(why, words):
    """Unknown is not half right: no points, no weight, and the detail says what it checks."""
    assert holds_up(ev(holds_up="unclear", holds_up_why=why)) == (None, words, None)
    out = rig_score(ev(holds_up="unclear", holds_up_why=why))
    assert out["score"] == 100 and "holds up" in out["formula"]["not_measured"]


def test_why_holds_up_is_unclear_from_a_row():
    from proving_ground.rig_score import holds_up_why

    assert holds_up_why({"held_out": {"tasks": 2, "diff": None, "n_pairs": 0}}) == "no_pairs"
    row = {"held_out": {"diff": -0.1, "n_pairs": 3}, "visible": {"diff": -0.6}}
    assert holds_up_why(row) == "no_gain"
    row = {"held_out": {"diff": -0.1, "n_pairs": 3}, "visible": {"diff": 0.05}}
    assert holds_up_why(row) == "mixed"
    assert holds_up_why({"held_out": {"diff": 0.2, "n_pairs": 3}, "visible": {}}) is None


def test_holds_up_without_held_out_tasks_is_not_measured():
    assert holds_up(ev(holds_up=None))[0] is None


def test_holds_up_verdict_from_a_row():
    assert holds_up_verdict({"held_out": None}) is None
    assert holds_up_verdict({"overfit": {"verdict": "overfit"}, "held_out": {}}) == "overfit"
    assert holds_up_verdict({"held_out": {"tasks": 2, "diff": None, "n_pairs": 0}}) == "unclear"
    row = {"held_out": {"diff": 0.2, "n_pairs": 3}, "visible": {"diff": 0.5}}
    assert holds_up_verdict(row) == "generalises"
    row = {"held_out": {"diff": 0.0, "n_pairs": 3}, "visible": {"diff": 0.5}}
    assert holds_up_verdict(row) == "overfit"
    row = {"held_out": {"diff": -0.1, "n_pairs": 3}, "visible": {"diff": 0.05}}
    assert holds_up_verdict(row) == "unclear"


# ---------- Reliable ----------


def test_reliable_is_the_share_of_clean_trials():
    s, detail, drag = reliable(ev(trials={"total": 20, "errored": 3, "broken": 1}))
    assert s == pytest.approx(80)
    assert detail == "16 of 20 trials ran cleanly"
    assert drag == "4 of 20 trials errored, broke, timed out or were cut off"


def test_an_uncalibrated_judge_loses_half_of_reliable():
    s, detail, drag = reliable(ev(judge={"trustworthy": False}))
    assert s == pytest.approx(100 * P["reliable"]["untrusted_judge"])
    assert detail.endswith("the judge isn't calibrated")
    assert drag == "the judge isn't calibrated as trustworthy"
    assert reliable(ev(judge={"trustworthy": True}))[0] == 100
    assert reliable(ev(trials={"total": 0}))[0] is None


# ---------- The whole score ----------


def test_a_rig_that_works_on_every_part():
    out = rig_score(ev())
    assert out["score"] == 100 and out["band"] == "works" and out["tone"] == "positive"
    assert out["label"] == "Works — use it"
    assert out["reason"] == "Every part holds up"
    assert out["gates"] == [] and not out["provisional"]
    unmeasured = rig_score(ev(adherence=None, holds_up=None))["reason"]
    assert unmeasured == "Every part holds up; not measured: followed, holds up"


def test_the_score_is_the_weighted_sum():
    out = rig_score(
        ev(ci_low=0.125, adherence={"read": 30, "steps_run": 0.5, "models_ok": 0.5, "steps": 4})
    )
    want = 100 - P["lift"]["weight"] * 50 - P["followed"]["weight"] * 50
    assert want == 72.5 and out["score"] == 73, "rounded half up"
    assert {p["id"]: p["score"] for p in out["parts"]} == {
        "lift": 50.0,
        "cost": 100.0,
        "followed": 50.0,
        "holds_up": 100.0,
        "reliable": 100.0,
    }


def test_missing_parts_are_left_out_and_the_rest_renormalised():
    out = rig_score(ev(ci_low=0.125, holds_up=None, adherence=None))
    w = P["lift"]["weight"] + P["cost"]["weight"] + P["reliable"]["weight"]
    want = (P["lift"]["weight"] * 50 + (P["cost"]["weight"] + P["reliable"]["weight"]) * 100) / w
    assert out["score"] == math.floor(want + 0.5)
    hold, fol = part(out, "holds_up"), part(out, "followed")
    assert hold["score"] is None and hold["detail"].startswith("This bench has no held-out tasks")
    assert fol["score"] is None and fol["detail"] == "no session logs to read"
    assert sum(p["weight_used"] for p in out["parts"]) == pytest.approx(1.0, abs=1e-3)
    assert hold["weight_used"] == 0


def test_nothing_measured_has_no_score():
    out = rig_score(ev(n_pairs=0, diff=None, ci_low=None, ci_high=None))
    assert out["score"] is None and out["band"] == "none"
    assert out["label"] == "Not Measured Yet"


def test_gate_hurts_caps_at_its_value():
    out = rig_score(ev(diff=-0.3, ci_low=-0.5, ci_high=-0.1, verdict="hurts"))
    assert out["score"] <= V["gates"]["hurts_cap"]
    assert [g["id"] for g in out["gates"]] == ["hurts", "not_shown"]
    assert out["band"] == "doesnt"
    assert out["label"] == "Doesn't Work — does worse than the plain agent (-30 pts)"


def test_an_interval_reaching_zero_is_not_proven_and_cost_and_reliable_earn_nothing():
    # Every other part perfect. Cost and Reliable count at 0 until a lift is shown, so only
    # Followed and Holds up score: 30, under the not-shown cap of 49 (which then doesn't bind).
    out = rig_score(ev(ci_low=-0.05, diff=0.2, verdict="inconclusive", pass_without=0.5))
    assert out["score"] == 30
    assert out["band"] == "not_proven" and out["tone"] == "warning"
    # What would settle it: the pairs a +20 pts lift needs at a 50% base rate (stats).
    assert out["label"] == "Not Proven — about 99 pairs would settle it (30 so far)"
    assert out["gates"][0]["text"] == "Capped at 49: not shown to help (the interval reaches 0)."
    assert out["gates"][0]["binding"] is False
    for pid in ("cost", "reliable"):
        p = part(out, pid)
        assert p["score"] == 100 and p["counted"] is False
        assert p["note"] == "counts once a lift is shown"
    assert part(out, "followed")["counted"] and part(out, "lift")["counted"]


def test_gate_few_pairs_is_provisional_but_still_scored():
    out = rig_score(ev(n_pairs=V["gates"]["min_pairs"] - 1))
    # A perfect run on too few pairs is promising, never "works".
    assert out["provisional"] and out["score"] == V["gates"]["provisional_cap"]
    assert out["band"] == "not_proven"
    assert out["label"] == "Not Proven — more pairs would settle it (9 so far)"
    assert (
        out["reason"]
        == f"Looks good on {V['gates']['min_pairs'] - 1} pairs; 10 are needed to call it working"
    )
    assert out["gates"][-1]["id"] == "provisional"
    assert not rig_score(ev(n_pairs=V["gates"]["min_pairs"]))["provisional"]


def test_bands_and_their_labels():
    # 60-79: names the weakest part.
    half = {"read": 30, "steps_run": 0.5, "models_ok": 0.5, "steps": 4}
    out = rig_score(ev(costs=costs(4.0, 1.0), adherence=half))
    assert 60 <= out["score"] < 80 and out["band"] == "works_but" and out["tone"] == "neutral"
    assert out["label"] == "Works, but cost needs work"
    assert out["reason"] == "Costs 4× the plain agent; the agent skipped 2 of 4 steps on average"
    # Under 60 with a lift shown: it helps, so never "doesn't work"; the biggest drag, concretely.
    out = rig_score(
        ev(trials={"total": 10, "errored": 10, "broken": 0}, ci_low=0.06, costs=costs(2.5, 1.0))
    )
    assert 40 <= out["score"] < 60 and out["band"] == "helps_but" and out["tone"] == "warning"
    assert out["label"] == "Helps, but lift could be as small as +6 pts"
    out = rig_score(
        ev(
            ci_low=0.01,
            costs=costs(30, 1.0),
            adherence={"read": 2, "steps_run": 0, "models_ok": 0, "steps": 3},
        )
    )
    assert out["score"] < 40 and out["band"] == "helps_but"
    assert out["label"] == "Helps, but lift could be as small as +1 pts"
    assert out["reason"] == (
        "Lift could be as small as +1 pts; costs 30× the plain agent; "
        "the agent skipped 3 of 3 steps on average"
    )


@pytest.mark.parametrize(
    ("low", "high", "verdict", "band"),
    [
        (0.3, 0.7, "helps", "works"),
        (-0.4, 0.6, "inconclusive", "not_proven"),
        (-0.79, 0.79, "inconclusive", "not_proven"),
        (-0.2, 0.05, "inconclusive", "not_proven"),  # +5 pts is reachable
        (-0.2, 0.04, "inconclusive", "doesnt"),  # it can't reach +5 pts
        (-0.3, 0.0, "inconclusive", "doesnt"),  # upper bound at 0
        (-0.6, -0.1, "hurts", "doesnt"),
        (0.01, 0.03, "helps", "doesnt"),  # shown, but too small to matter
    ],
)
def test_the_band_comes_from_the_interval_first(low, high, verdict, band):
    out = rig_score(ev(ci_low=low, ci_high=high, diff=(low + high) / 2, verdict=verdict))
    assert out["band"] == band
    tone = next(b["tone"] for b in V["bands"] if b["id"] == band)
    assert out["tone"] == tone, "the tone is the band's, whatever the number"


def test_an_interval_spanning_zero_never_reads_doesnt_work():
    for low in (-0.9, -0.5, -0.1, 0.0):
        for high in (0.05, 0.1, 0.4, 0.9):
            for extra in ({}, {"costs": costs(40, 1.0)}, {"n_pairs": 2}):
                out = rig_score(
                    ev(ci_low=low, ci_high=high, diff=0.0, verdict="inconclusive") | extra
                )
                assert out["band"] == "not_proven", (low, high, extra)
                assert not out["label"].startswith("Doesn't Work")


def test_doesnt_work_says_why_from_the_interval():
    out = rig_score(ev(ci_low=-0.2, ci_high=0.03, diff=-0.08, verdict="inconclusive"))
    assert out["label"] == (
        "Doesn't Work — the lift can't reach +5 pts (the interval's upper bound is +3)"
    )
    out = rig_score(ev(ci_low=-0.3, ci_high=0.0, diff=-0.15, verdict="inconclusive"))
    assert out["label"] == "Doesn't Work — no lift: even the interval's upper bound is +0 pts"
    out = rig_score(ev(ci_low=-0.2, ci_high=0.5, diff=-0.1, verdict="inconclusive", n_pairs=4))
    assert out["label"] == "Not Proven — no lift seen in 4 pairs yet; more pairs would settle it"


@pytest.mark.parametrize(
    ("status", "badge", "reason"),
    [
        (
            "invalid",
            "Invalid: the check is broken",
            "Not a command, so every trial fails both ways: a.",
        ),
        (
            "uninformative",
            "Uninformative: both always pass",
            "No task could be won or lost, so it says nothing.",
        ),
    ],
)
def test_a_result_that_is_not_evidence_gets_no_score(status, badge, reason):
    # No number, no band and no formula: only why it isn't evidence.
    out = rig_score(ev(validity={"status": status, "badge": badge, "reason": reason}))
    assert out["score"] is None and out["band"] == "not_evidence" and out["tone"] == "neutral"
    assert out["label"] == "Not Evidence"
    assert out["reason"] == f"{badge}. {reason}"
    assert out["formula"] is None and out["gates"] == []
    assert all(p["counted"] is False for p in out["parts"])
    assert (
        rig_score(ev(validity={"status": "valid", "badge": None, "reason": None}))["score"] == 100
    )


def test_the_formula_rebuilds_the_number():
    out = rig_score(ev(ci_low=0.125, holds_up=None, costs=costs(2.0, 1.0)))
    f = out["formula"]
    assert f["measured_weight"] == pytest.approx(0.85) and f["not_measured"] == ["holds up"]
    rebuilt = sum(p["weight"] * p["score"] for p in out["parts"] if p["counted"]) / 0.85
    assert rebuilt == pytest.approx(f["raw"], abs=0.01)
    assert out["score"] == math.floor(rebuilt + 0.5)
    assert f["text"].startswith("40% × 50 + 20% × ")
    assert "÷ 85% (weights rescaled to the measured parts; holds up not measured)" in f["text"]
    assert f["text"].endswith(f"rounded: {out['score']}")
    # All five measured: no rescaling; a binding cap is in the formula.
    f = rig_score(ev(n_pairs=4))["formula"]
    assert "rescaled" not in f["text"] and "capped at 59 (too few pairs)" in f["text"]
    # No credit is written as such.
    f = rig_score(ev(ci_low=-0.1, diff=0.1, verdict="inconclusive"))["formula"]
    assert "20% × 0 (Cost: no credit yet)" in f["text"]
    assert "10% × 0 (Reliable: no credit yet)" in f["text"]


def test_the_reason_lists_at_most_three_drags_most_points_first():
    out = rig_score(
        ev(
            ci_low=-0.1,
            diff=0.0,
            verdict="inconclusive",
            costs=costs(20, 1.0),
            adherence={"read": 2, "steps_run": 0.0, "models_ok": 0.0, "steps": 2},
            holds_up="overfit",
            trials={"total": 10, "errored": 5, "broken": 0},
        )
    )
    assert out["reason"] == (
        "No lift shown; costs 20× the plain agent; the agent skipped 2 of 2 steps on average"
    )


def test_same_evidence_same_score():
    e = ev(ci_low=0.1, costs=costs(2.2, 1.0), holds_up="unclear", holds_up_why="no_pairs")
    frozen = copy.deepcopy(e)
    a, b = rig_score(e), rig_score(e)
    assert a == b and e == frozen, "pure: same answer, input untouched"


def test_regression_lab_bugfix_fix_a_bug():
    """The real run: Lab bugfix with "Fix a bug". Both arms solved both tasks, so nothing to
    gain; the workflow cost $2.83 against $0.07 and ran 1 of its 5 steps."""
    out = rig_score(
        {
            "kind": "workflow",
            "n_pairs": 2,
            "diff": 0.0,
            "ci_low": -0.79,
            "ci_high": 0.79,
            "verdict": "inconclusive",
            "costs": {
                "with": {"spent_usd": 2.83, "solved": 2, "tasks": 2},
                "without": {"spent_usd": 0.07, "solved": 2, "tasks": 2},
            },
            "local": False,
            "adherence": {
                "trials": 2,
                "read": 2,
                "followed": 0,
                "steps_run": 0.2,
                "models_ok": 0.2,
                "steps": 5,
                "not_opened": 0,
                "missing": ["Find the cause", "Write a test", "Fix", "Review"],
            },
            "holds_up": None,
            "trials": {"total": 4, "errored": 0, "broken": 0},
            "judge": None,
        }
    )
    # The interval (-79 to +79) reaches far past 0 both ways: not proven, never "doesn't work".
    # Cost (40×) and Reliable (clean) count at 0 with no lift shown: 15% × 20 ÷ 85% = 3.5.
    assert out["score"] == 4
    assert out["band"] == "not_proven" and out["tone"] == "warning"
    assert out["label"] == "Not Proven — no lift seen in 2 pairs yet; more pairs would settle it"
    assert out["reason"] == (
        "No lift shown; costs 40× the plain agent; the agent skipped 4 of 5 steps on average"
    )
    assert out["provisional"] and out["pairs"] == 2
    assert part(out, "cost")["detail"] == "40.4× the plain agent's cost per solved task"
    assert part(out, "holds_up")["score"] is None


def test_regression_the_same_run_is_uninformative_so_it_is_not_evidence():
    """Both arms solved both tasks: validity calls it uninformative, so it gets no score."""
    uninformative = {
        "status": "uninformative",
        "badge": "Uninformative: both always pass",
        "reason": "No task could be won or lost, so it says nothing.",
    }
    out = rig_score(ev(n_pairs=2, ci_low=-0.79, ci_high=0.79, diff=0.0, validity=uninformative))
    assert out["score"] is None and out["label"] == "Not Evidence"
    assert out["reason"].startswith("Uninformative: both always pass")


def test_evidence_from_a_lab_row_and_a_pooled_suite():
    row = {
        "n_pairs": 4,
        "diff": 0.5,
        "ci_low": 0.1,
        "ci_high": 0.8,
        "verdict": "helps",
        "costs": costs(2.0, 1.0, tasks=4),
        "adherence": {"read": 4, "steps_run": 0.5, "models_ok": 0.5, "steps": 2},
        "held_out": {"tasks": 1, "diff": 0.3, "n_pairs": 1},
        "visible": {"diff": 0.6},
        "trials": {"total": 8, "errored": 1, "broken": 0},
        "judge": {"trustworthy": True},
    }
    e = evidence_from_row(row)
    assert e["holds_up"] == "generalises" and e["trials"]["errored"] == 1
    other = row | {
        "adherence": {"read": 2, "steps_run": 1.0, "models_ok": 1.0, "steps": 2},
        "held_out": None,
        "judge": {"trustworthy": False},
    }
    pooled = pool_evidence(
        [row, other], {"n_pairs": 8, "diff": 0.5, "ci_low": 0.2, "ci_high": 0.7, "verdict": "helps"}
    )
    assert pooled["costs"]["with"] == {"spent_usd": 4.0, "solved": 20, "tasks": 8}
    assert pooled["trials"] == {"total": 16, "errored": 2, "broken": 0}
    assert pooled["adherence"]["steps_run"] == pytest.approx((0.5 * 4 + 1.0 * 2) / 6, abs=0.01)
    assert pooled["holds_up"] == "generalises"
    assert pooled["judge"] == {"trustworthy": False}
    assert rig_score(pooled)["score"] is not None


# ---------- On every result payload ----------


def test_lab_results_proven_and_build_md_carry_the_score(tmp_path, monkeypatch):
    from test_api_workspace import ORIGIN
    from test_bench import _lab_client, _starter, _wait

    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    wf = _starter(c, "Fix a bug")
    c.post("/api/lab/save", json=wf, headers=ORIGIN)
    r = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "bugfix", "budget": 5, "auto": False},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    row = _wait(c, 1)[0]
    rig = row["rig"]
    assert rig == rig_score(evidence_from_row(row)), "the row's score is the pure function's"
    assert [p["id"] for p in rig["parts"]] == list(P)
    # Same spend on both arms; the fake leaves no session logs, so Followed isn't measured.
    assert part(rig, "cost")["detail"] == "1.0× the plain agent's cost per task"
    assert part(rig, "followed")["score"] is None
    assert rig["score"] == 59 and rig["provisional"] and rig["pairs"] == row["n_pairs"]
    folder = tmp_path / "home" / "library" / "workflows" / f"workflow-{wf['id']}"
    assert (
        f"| 59 Not Proven — more pairs would settle it ({row['n_pairs']} so far) (provisional) |"
        in (folder / "PROVEN.md").read_text()
    )
    assert c.get("/api/lab").json()["saved"][0]["proven"]["rig"] == 59
    spec = c.post("/api/buildspec", json={"source": "workflow", "workflow": wf}, headers=ORIGIN)
    md = spec.json()["markdown"]
    assert "| measured | change (points) | pairs | verdict | Rig score |" in md
    assert "59/100 Not Proven — more pairs would settle it (" in md
    assert spec.json()["json"]["evals"]["latest"][0]["rig"]["score"] == 59


def test_repo_experiments_carry_the_score(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from test_api_runs import events, fake_result
    from test_api_workspace import BASE, ORIGIN

    from proving_ground.api.app import create_app
    from proving_ground.files import save_scenario
    from proving_ground.models import Scenario

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    root = tmp_path / "proj"
    root.mkdir()
    (root / "app.py").write_text("x")
    save_scenario(root, Scenario(id="a", instruction="Fix.", check="true", check_status="approved"))
    sk = tmp_path / "skills" / "tdd"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("---\nname: tdd\n---\nTest first.\n")
    monkeypatch.setattr(
        "proving_ground.runner.harbor.harbor_executor",
        lambda req: fake_result(0.0 if req.agent == "nop" else (1.0 if req.skills else 0.0)),
    )
    c = TestClient(create_app(root), base_url=BASE)
    body = {"treatment_path": str(sk), "n": 6, "budget": 100}
    assert c.post("/api/experiments", json=body, headers=ORIGIN).status_code == 200
    events(c, 1)
    detail = c.get("/api/experiments/1").json()
    rig = detail["rig"]
    # Every trial cost $0.50: with solved 6 of 6, without 0 of 6, so cost is compared per task.
    assert part(rig, "cost")["score"] == 100
    assert part(rig, "cost")["detail"] == "1.0× the plain agent's cost per task"
    assert part(rig, "followed")["detail"] == "no session logs to read"
    assert rig["score"] is not None and rig["provisional"]
    assert c.get("/api/experiments").json()[0]["rig"] == rig


def test_skill_opened_reads_the_session_logs(tmp_path):
    import json

    from proving_ground.adherence import skill_opened

    assert skill_opened(tmp_path, "tdd") is None
    log = tmp_path / "agent" / "sessions" / "s.jsonl"
    log.parent.mkdir(parents=True)

    def say(*blocks):
        log.write_text("\n".join(json.dumps({"message": {"content": [b]}}) for b in blocks) + "\n")

    say({"type": "tool_use", "name": "Bash", "input": {"command": "ls"}})
    assert skill_opened(tmp_path, "tdd") is False
    say({"type": "tool_use", "name": "Skill", "input": {"skill": "tdd"}})
    assert skill_opened(tmp_path, "tdd") is True
    say(
        {
            "type": "tool_use",
            "name": "Read",
            "input": {"file_path": "/x/.claude/skills/tdd/SKILL.md"},
        }
    )
    assert skill_opened(tmp_path, "tdd") is True


# ---------- one trial ledger per result ----------


def _t(sid, arm, outcome, rep=0):
    from proving_ground.models import ScenarioKind
    from proving_ground.trial import TrialOutcome

    return TrialOutcome(sid, ScenarioKind.TYPICAL, arm, rep, outcome, cost_usd=0.1)


def test_the_ledger_counts_every_trial_once_and_every_line_cites_it():
    from proving_ground.rig_score import ledger, ledger_text

    # 5 trials, 3 "with" (logs read for all 3), 2 complete pairs.
    trials = [
        _t("a", "with", "pass"),
        _t("a", "without", "fail"),
        _t("b", "with", "pass"),
        _t("b", "without", "pass"),
        _t("c", "with", "fail"),  # its "without" never ran: not a pair
    ]
    ld = ledger(trials, logs_read=3)
    assert ld == {
        "total": 5,
        "with": 3,
        "without": 2,
        "pairs": 2,
        "logs_read": 3,
        "clean": 5,
        "timed_out": 0,
        "errored": 0,
        "broken": 0,
    }
    assert ld["with"] + ld["without"] == ld["total"]
    assert ld["clean"] + ld["timed_out"] + ld["errored"] + ld["broken"] == ld["total"]
    assert ledger_text(ld) == (
        "5 trials (3 with, 2 without) · 2 complete pairs · 5 ran cleanly · logs read for 3 of "
        'the 3 "with" trials'
    )
    out = rig_score(
        ev(
            n_pairs=ld["pairs"],
            ledger=ld,
            adherence={"read": ld["logs_read"], "steps_run": 0.2, "models_ok": 0.2, "steps": 5},
        )
    )
    assert out["pairs"] == ld["pairs"] and out["ledger"] == ld
    assert part(out, "reliable")["detail"] == "5 of 5 trials ran cleanly (3 with, 2 without)"
    assert 'in the 3 "with" trials whose logs could be read' in part(out, "followed")["detail"]
    assert out["ledger_text"] == ledger_text(ld)


def test_the_ledger_counts_errored_and_broken_trials():
    from proving_ground.rig_score import ledger, ledger_text

    ld = ledger([_t("a", "with", "errored"), _t("a", "without", "pass"), _t("b", "with", "broken")])
    assert (ld["clean"], ld["errored"], ld["broken"], ld["pairs"]) == (1, 1, 1, 0)
    assert (
        ledger_text(ld)
        == "3 trials (2 with, 1 without) · 0 complete pairs · 1 ran cleanly, 1 errored, 1 broken"
    )


def test_pooled_ledgers_add_up_and_a_pool_with_a_non_evidence_bench_is_not_evidence():
    from proving_ground.rig_score import ledger

    a = {
        "bench": "qa",
        "n_pairs": 2,
        "ledger": ledger([_t("a", "with", "pass"), _t("a", "without", "fail")], 1),
    }
    b = {
        "bench": "bugfix",
        "bench_name": "Fix bugs",
        "n_pairs": 1,
        "ledger": ledger([_t("x", "with", "pass"), _t("x", "without", "pass")], 1),
        "validity": {"status": "uninformative", "badge": "Uninformative: both always pass"},
    }
    pooled = pool_evidence([a, b], {"n_pairs": 2, "diff": 0.5, "ci_low": 0.1, "ci_high": 0.8})
    assert pooled["ledger"]["total"] == 4 and pooled["ledger"]["logs_read"] == 2
    out = rig_score(pooled)
    assert out["score"] is None and out["band"] == "not_evidence"
    assert "Fix bugs: Uninformative: both always pass" in out["reason"]


# ---------- the API: one ledger, a read-only run link, the shipped result ----------


def test_lab_rows_carry_one_ledger_and_the_run_has_its_own_read_only_link(tmp_path, monkeypatch):
    from test_api_workspace import ORIGIN
    from test_bench import _lab_client, _starter, _wait

    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    a, b = _starter(c, "Fix a bug"), _starter(c, "Refactor safely")
    for wf in (a, b):
        r = c.post(
            "/api/lab/run",
            json={"workflow": wf, "bench": "qa", "budget": 5, "auto": False},
            headers=ORIGIN,
        )
        assert r.status_code == 200, r.text
        _wait(c, 1 if wf is a else 2)
    rows = _wait(c, 2)
    for row in rows:
        ld = row["ledger"]
        assert ld["pairs"] == row["n_pairs"] == row["rig"]["pairs"]
        assert ld["total"] == row["trials"]["total"] and ld["with"] + ld["without"] == ld["total"]
        assert row["rig"]["ledger"] == ld
        assert row["over_budget"] is None  # it kept to its $5
    one = rows[0]
    got = c.get(f"/api/lab/results/{one['bench']}/{one['id']}").json()
    assert got["rig"] == one["rig"] and got["ledger"] == one["ledger"]
    assert len(got["trials"]) == one["ledger"]["total"]
    assert got["summary"]["headline"]["n_pairs"] == one["n_pairs"]
    assert c.get(f"/api/lab/results/{one['bench']}/999").status_code == 404
    assert c.get("/api/lab/results/nope/1").status_code == 404

    # Ship: the header's result is this workflow's own, never the other one's.
    for wf in (a, b):
        spec = c.post("/api/buildspec", json={"source": "workflow", "workflow": wf}, headers=ORIGIN)
        shipped = spec.json()["shipped"]
        mine = next(r for r in rows if r["workflow_id"] == wf["id"])
        assert shipped == {"name": wf["name"], "where": mine["bench_name"], "rig": mine["rig"]}
    other = {**a, "id": "never-measured", "name": "Never measured"}
    spec = c.post("/api/buildspec", json={"source": "workflow", "workflow": other}, headers=ORIGIN)
    assert spec.json()["shipped"] is None


def test_repo_runs_carry_validity_and_the_ship_header_is_scoped_to_the_canvas(
    tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient
    from test_api_runs import events, fake_result
    from test_api_workspace import BASE, ORIGIN

    from proving_ground.api.app import create_app
    from proving_ground.files import save_scenario
    from proving_ground.models import Scenario

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    root = tmp_path / "proj"
    root.mkdir()
    (root / "app.py").write_text("x")
    save_scenario(root, Scenario(id="a", instruction="Fix.", check="true", check_status="approved"))
    sk = tmp_path / "skills" / "tdd"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("---\nname: tdd\n---\nTest first.\n")
    # Both arms always pass: uninformative, so not evidence and no score.
    monkeypatch.setattr(
        "proving_ground.runner.harbor.harbor_executor",
        lambda req: fake_result(0.0 if req.agent == "nop" else 1.0),
    )
    c = TestClient(create_app(root), base_url=BASE)
    body = {"treatment_path": str(sk), "n": 2, "budget": 100}
    assert c.post("/api/experiments", json=body, headers=ORIGIN).status_code == 200
    events(c, 1)
    row = c.get("/api/experiments").json()[0]
    assert row["validity"]["status"] == "uninformative"
    assert row["rig"]["score"] is None and row["rig"]["band"] == "not_evidence"
    assert row["ledger"]["total"] == 4 and row["over_budget"] is None
    detail = c.get("/api/experiments/1").json()
    assert detail["validity"] == row["validity"] and detail["rig"] == row["rig"]

    # tdd isn't on this repo's canvas: the Ship header has nothing to show for it.
    spec = c.post("/api/buildspec", json={"source": "repo"}, headers=ORIGIN).json()
    assert spec["shipped"] is None
    added = {"skills": [{"name": "tdd", "path": str(sk)}]}
    spec = c.post("/api/buildspec", json={"source": "repo", "added": added}, headers=ORIGIN).json()
    assert spec["shipped"]["name"] == "tdd" and spec["shipped"]["rig"] == row["rig"]
    assert "| tdd |" in spec["markdown"] and "not evidence" in spec["markdown"]
