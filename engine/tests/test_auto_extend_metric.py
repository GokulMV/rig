"""Auto-extend on a run scored on a saving: it decides on the saving and its pass-rate guard at
the stricter interval, not on the pass rate excluding zero (judge-experiment: Auto-extend)."""

import json
from pathlib import Path
from types import SimpleNamespace

from test_api_workspace import ORIGIN
from test_bench import _lab_client, _starter, _wait
from test_lab_metric import tokens_fake

import proving_ground.runner.harbor as harbor
from proving_ground import rig_score, stats
from proving_ground.models import ScenarioKind
from proving_ground.trial import TrialOutcome

Z = stats.J["auto_extend"]["stop_z"]


def pairs(n, w_tok, wo_tok, w_pass=True, wo_pass=True):
    out = []
    for i in range(n):
        for arm, tok, ok in (("with", w_tok, w_pass), ("without", wo_tok, wo_pass)):
            out.append(
                TrialOutcome(f"s{i}", ScenarioKind.TYPICAL, arm, 0, "pass" if ok else "fail", tok)
            )
    return out


def test_t_two_sided_is_students_t():
    # Two-sided 99% (the 0.995 quantile), from any t table.
    for df, t in ((1, 63.657), (5, 4.032), (10, 3.169), (30, 2.750), (100, 2.626)):
        assert abs(stats.t_two_sided(df, 0.99) - t) < 1e-3
    # At 95% it is the table auto-extend's 95% interval already uses, unrounded.
    assert all(abs(stats.t_two_sided(df, 0.95) - stats.t975(df)) < 1e-3 for df in range(1, 40))


def test_the_saving_and_the_guard_both_decide_at_the_stricter_interval():
    # A third of the tokens, every pair passing both ways: the cut is shown at once (each pair
    # alike: a point interval), and the guard is the 99% Newcombe bound on n agreeing pairs,
    # above -10 pts from 60 pairs (59: -10.1).
    assert stats.paired_diff_ci(stats.PairCounts(59, 0, 0, 0), Z)[1] * 100 < -10
    assert stats.paired_diff_ci(stats.PairCounts(60, 0, 0, 0), Z)[1] * 100 > -10
    got = rig_score.metric_stop(pairs(59, 10_000, 30_000), "tokens", Z)
    assert got == {"why": None, "waiting": ["guard"], "pairs": 59}
    assert rig_score.metric_stop(pairs(60, 10_000, 30_000), "tokens", Z)["why"] == "both"


def test_an_answer_that_is_doesnt_help_stops_it_whatever_the_other_says():
    # The same tokens both ways: the best cut is 0%, under the 5% that can matter.
    assert rig_score.metric_stop(pairs(4, 20_000, 20_000), "tokens", Z)["why"] == "too_small"
    # Twice the tokens with it: higher, shown.
    assert rig_score.metric_stop(pairs(4, 40_000, 20_000), "tokens", Z)["why"] == "worse"
    # Every pair fails with it and passes without: the pass rate is shown lower (4 pairs: the
    # 99% upper bound is -12 pts).
    assert stats.paired_diff_ci(stats.PairCounts(0, 0, 4, 0), Z)[2] < 0
    assert rig_score.metric_stop(pairs(4, 1, 1, w_pass=False), "tokens", Z)["why"] == "hurts"
    # Nothing recorded on an arm: no number of pairs settles that.
    assert rig_score.metric_stop(pairs(4, 0, 0), "tokens", Z)["why"] == "unrecorded"


def test_a_settled_pass_rate_does_not_decide_a_saving():
    # With always passes, without never does: the pass rate is decided at 99% from 3 pairs, but
    # the baseline solved nothing, so there is no tokens per solved task to compare yet.
    trials = pairs(4, 10, 10, wo_pass=False)
    assert stats.stop_verdict(trials, Z)[0] is stats.Verdict.HELPS
    assert rig_score.metric_stop(trials, "tokens", Z) == {
        "why": None,
        "waiting": ["saving"],
        "pairs": 4,
    }
    # Too few pairs for either: it waits on both.
    assert rig_score.metric_stop(pairs(1, 10, 30), "tokens", Z)["waiting"] == ["saving", "guard"]


def test_the_guard_on_partial_credit_uses_the_stricter_paired_t():
    def scored(n):
        out = []
        for i in range(n):
            for arm, right in (("with", 10 + i % 2), ("without", 10)):
                out.append(
                    TrialOutcome(
                        f"s{i}", ScenarioKind.TYPICAL, arm, 0, "pass", 1, items_right=right,
                        items_total=12,
                    )  # fmt: skip
                )
        return out

    trials = scored(8)
    real = stats.real_pairs(trials)
    at95 = stats.item_stats(real)
    at99 = stats.item_stats(real, z=Z)
    assert at95.diff == at99.diff and at99.ci_low < at95.ci_low and at99.ci_high > at95.ci_high
    # Differences 0, 1/12, 0, 1/12, ...: mean 1/24, sd sqrt(8/7)/24; t(7) at 99% is 3.499.
    half = 3.4995 * (8 / 7) ** 0.5 / 24 / 8**0.5
    assert abs(at99.ci_low - (1 / 24 - half)) < 1e-3
    assert stats.stop_quality(trials, Z) == (at99.ci_low, at99.ci_high, 8)


def events(c, bench, eid) -> list[dict]:
    text = c.get(f"/api/lab/runs/{bench}/{eid}/events").text
    return [json.loads(x[6:]) for x in text.splitlines() if x.startswith("data: ")]


def test_a_run_on_tokens_keeps_going_until_the_guard_is_decided(tmp_path: Path, monkeypatch):
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)
    monkeypatch.setattr(harbor, "harbor_executor", tokens_fake)  # a third of the tokens, all pass
    wf = _starter(c, "Fix a bug")
    r = c.post(
        "/api/lab/run",
        json={"workflow": wf, "bench": "qa", "budget": 50, "auto": True, "metric": "tokens"},
        headers=ORIGIN,
    ).json()
    row = _wait(c, 1)[0]
    ev = events(c, "qa", r["id"])
    grew = [e for e in ev if e["type"] == "extended"]
    # qa has 2 tasks: each look adds 5 repeats (10 pairs, `metric.step_pairs`): 2, 12, ... 52
    # wait on the guard (the cut is shown from the start); at 62 both are decided (60 needed).
    assert [e["pairs"] for e in grew] == [2, 12, 22, 32, 42, 52]
    assert all(e["waiting"] == "the pass-rate guard" for e in grew)
    settled = next(e for e in ev if e["type"] == "settled")
    assert settled["pairs"] == 62 and row["n_pairs"] == 62
    assert settled["reason"] == (
        "the cut in tokens per solved task and the pass-rate guard are both decided at the "
        "stricter interval"
    )
    # The 95% result credits the saving: the guard holds and the cut is a third.
    assert row["rig"]["metric"]["noninferior"] is True
    assert row["rig"]["verdict"]["id"] == "helps"


def test_a_run_on_tokens_doesnt_stop_when_only_the_pass_rate_is_settled(
    tmp_path: Path, monkeypatch
):
    def fake(req):  # with always passes, without never: no tokens per solved task without
        ok = req.agent != "nop" and bool(req.skills)
        return SimpleNamespace(
            exception_info=None,
            verifier_result=SimpleNamespace(rewards={"reward": 1.0 if ok else 0.0}),
            agent_result=SimpleNamespace(n_input_tokens=1_000, n_output_tokens=0, cost_usd=0.02),
            started_at=None,
            finished_at=None,
            trial_name="fake",
        )

    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)
    monkeypatch.setattr(harbor, "harbor_executor", fake)
    wf = _starter(c, "Fix a bug")
    body = {"workflow": wf, "bench": "qa", "budget": 50, "auto": True}
    plain = c.post("/api/lab/run", json=body, headers=ORIGIN).json()
    _wait(c, 1)
    on_pass_rate = next(e for e in events(c, "qa", plain["id"]) if e["type"] == "settled")
    # The pass rate, unchanged: 2 pairs are short at 99%, 4 decide it.
    assert on_pass_rate == {
        "type": "settled",
        "reason": "decided at the stricter interval (helps)",
        "pairs": 4,
        "looks": 1,
    }
    assert all("waiting" not in e for e in events(c, "qa", plain["id"]))
    saving = c.post("/api/lab/run", json=body | {"metric": "tokens"}, headers=ORIGIN).json()
    _wait(c, 2)
    ev = events(c, "qa", saving["id"])
    settled = next(e for e in ev if e["type"] == "settled")
    # 2, 12, ... 92: the next look would pass `metric.max_pairs` (100), still waiting on the saving.
    assert settled["pairs"] == 92
    assert settled["reason"] == "reached 92 pairs, with the saving still undecided"
    assert {e["waiting"] for e in ev if e["type"] == "extended"} == {"the saving"}


def test_keep_going_says_what_it_waits_for(tmp_path: Path, monkeypatch):
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)
    k = c.get("/api/rig-score").json()["metric"]["keep_going"]
    assert k["pass_rate"].endswith("Stops early only when a stricter (99%) interval rules out zero.")
    assert k["tokens"].startswith(
        "adds pairs until the saving and the pass-rate guard are both decided, up to the budget "
        "or 100 pairs."
    )
    assert "or tokens per solved task higher." in k["tokens"] and "time per solved" in k["time"]
    wf = _starter(c, "Fix a bug")
    est = {"pairs": 2, "bench": "qa", "workflow": wf, "size": "pilot", "tasks": 2, "budget": 5}
    plan = c.post(
        "/api/runs/estimate", json=est | {"metric": "tokens", "auto": True}, headers=ORIGIN
    ).json()["metric_plan"]
    assert plan["extends"] is True and plan["lines"][1].startswith(
        "This run plans 2 pairs; with \"Keep going until it's decided\" on, it adds pairs until"
    )
    off = c.post("/api/runs/estimate", json=est | {"metric": "tokens"}, headers=ORIGIN).json()
    assert off["metric_plan"]["extends"] is False
    assert "no saving can be credited" in off["metric_plan"]["lines"][1]
