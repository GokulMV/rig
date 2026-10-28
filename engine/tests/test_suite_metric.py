"""A Lab suite scored on tokens, cost or time: the saving pooled over every bench's pairs, its
bootstrap stratified by bench, and the pooled pass rate as the guard (rig-score: Metric, Suites)."""

from pathlib import Path

from test_api_workspace import ORIGIN
from test_bench import _lab_client, _starter, _suite_wait
from test_lab_metric import lab_meta, tokens_fake

import proving_ground.runner.harbor as harbor
from proving_ground import rig_score, stats, suite
from proving_ground.models import ScenarioKind
from proving_ground.trial import TrialOutcome

B = rig_score.M["bootstrap"]


def pairs(n, w_tokens, wo_tokens, w_pass=True, wo_pass=True, reused_from=None, cost=0.0):
    """n pairs on tasks s0..s{n-1}, every trial the same."""
    out = []
    for i in range(n):
        for arm, tok, ok in (("with", w_tokens, w_pass), ("without", wo_tokens, wo_pass)):
            out.append(
                TrialOutcome(
                    f"s{i}", ScenarioKind.TYPICAL, arm, 0, "pass" if ok else "fail", tok, 0,
                    cost, 1.0, reused_from=reused_from if arm == "without" else None,
                )  # fmt: skip
            )
    return out


def test_one_stratum_is_the_single_runs_bootstrap_draw_for_draw():
    rows = [(10.0, 1, 20.0, 1), (5.0, 1, 30.0, 0), (40.0, 0, 25.0, 1), (12.0, 1, 18.0, 1)]
    one = stats.paired_ratio_ci(rows, B["resamples"], B["seed"], B["min_pairs"])
    assert stats.stratified_ratio_ci([rows], B["resamples"], B["seed"], B["min_pairs"]) == one
    # Empty strata (a bench with no pairs yet) change nothing.
    assert stats.stratified_ratio_ci([[], rows, []], B["resamples"], B["seed"]) == one


def test_the_bootstrap_resamples_each_bench_within_itself():
    # Bench a: 2 pairs, 10 tokens with vs 20 without. Bench b: 3 pairs, 30 both ways. All solved.
    a = [(10.0, 1, 20.0, 1)] * 2
    b = [(30.0, 1, 30.0, 1)] * 3
    # Pooled: with (2·10 + 3·30) / 5 = 22, without (2·20 + 3·30) / 5 = 26: 22 / 26 = 11 / 13.
    ratio, lo, hi = stats.stratified_ratio_ci([a, b], B["resamples"], B["seed"])
    assert abs(ratio - 11 / 13) < 1e-12
    # Each bench's pairs are all alike, so every stratified resample is the pool itself: no spread.
    assert lo == hi == ratio
    # Resampling the union instead lets the mix of benches move (anything from 5 of a's pairs,
    # ratio 0.5, to 5 of b's, ratio 1): a spread the suite, which fixed 2 and 3, never had.
    _, ulo, uhi = stats.paired_ratio_ci(a + b, B["resamples"], B["seed"])
    assert ulo < 11 / 13 - 0.05 and uhi > 11 / 13 + 0.05


def test_the_stricter_level_widens_the_interval():
    rows = [(10.0 + i, 1, 20.0 - (i % 4), 1) for i in range(12)]
    _, lo95, hi95 = stats.paired_ratio_ci(rows, B["resamples"], B["seed"])
    _, lo99, hi99 = stats.paired_ratio_ci(rows, B["resamples"], B["seed"], level=0.99)
    assert lo99 <= lo95 < hi95 <= hi99 and (lo99, hi99) != (lo95, hi95)


def test_pool_metric_keeps_benches_apart_and_prices_reused_trials_where_they_ran():
    # Both benches use task ids s0..: pooled by bench, their pairs never merge.
    a = pairs(2, 10_000, 20_000)
    b = pairs(3, 30_000, 30_000)
    m = suite.pool_metric({"a": (a, None), "b": (b, None)}, "tokens")
    assert m["n"] == 5 and m["solved_with"] == m["solved_without"] == 5
    assert m["with"] == 22_000 and m["without"] == 26_000
    assert abs(m["ratio"] - 11 / 13) < 1e-12 and m["low"] == m["high"] == m["ratio"]
    assert suite.pool_metric({"a": (a, None)}, "pass_rate") is None
    # On cost, a reused "without" trial counts at what its own bench's source run paid.
    ra = pairs(2, 1, 1, cost=0.10, reused_from=7)
    rb = pairs(2, 1, 1, cost=0.10)
    got = suite.pool_metric({"a": (ra, lambda t: 0.30), "b": (rb, lambda t: 0.0)}, "cost")
    # with: 4 × 0.10 / 4 solved; without: (2 × 0.30 + 2 × 0.10) / 4: 0.10 / 0.20.
    assert abs(got["without"] - 0.20) < 1e-12 and abs(got["ratio"] - 0.5) < 1e-12


def test_a_bench_that_recorded_nothing_makes_the_pool_unrecorded():
    m = suite.pool_metric(
        {"a": (pairs(2, 10, 20), None), "b": (pairs(2, 0, 0), None)}, "tokens"
    )
    assert m == {"id": "tokens", "n": 4, "missing": "unrecorded"}
    # One that ran no pair yet is simply not in it.
    m = suite.pool_metric({"a": (pairs(2, 10, 20), None), "b": ([], None)}, "tokens")
    assert m["n"] == 2 and m["ratio"] == 0.5


def test_a_bench_where_both_always_pass_is_evidence_for_a_pooled_saving():
    row = {
        "bench": "a",
        "n_pairs": 4,
        "validity": {"status": "uninformative", "badge": "Both always pass", "cause": "both_pass"},
    }
    pooled = {"n_pairs": 4, "diff": 0.0, "ci_low": -0.3, "ci_high": 0.3, "verdict": "inconclusive"}
    assert rig_score.pool_evidence([row], pooled)["validity"]["status"] == "invalid"
    m = suite.pool_metric({"a": (pairs(4, 10, 20), None)}, "tokens")
    ev = rig_score.pool_evidence([row], pooled, m)
    assert ev["validity"] is None and ev["metric"] is m


def test_a_suite_on_tokens_pools_the_saving_and_guards_it_with_the_pooled_pass_rate(
    tmp_path: Path, monkeypatch
):
    from proving_ground import bench as bench_mod

    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)
    monkeypatch.setattr(harbor, "harbor_executor", tokens_fake)  # 10k with, 30k without, all pass
    wf = _starter(c, "Fix a bug")
    r = c.post(
        "/api/lab/suite", json={"workflow": wf, "budget": 50, "metric": "tokens"}, headers=ORIGIN
    )
    assert r.status_code == 200, r.text
    assert r.json()["metric"] == "tokens"
    v = _suite_wait(c, r.json()["job"])
    assert v["status"] == "done" and v["metric"] == "tokens"
    measured = [b for b in v["benches"] if b["n_pairs"]]
    assert len(measured) >= 2
    tasks = {b.id: len(b.scenarios) for b in bench_mod.benches()}
    for b in measured:
        # Each bench's own run is on tokens, and runs its planned pilot: no auto-extend per bench.
        assert lab_meta(tmp_path, b["bench"], b["experiment"])["metric"] == "tokens"
        assert b["n_pairs"] == tasks[b["bench"]]
        assert b["rig"]["metric"]["id"] == "tokens"
    p = v["pooled"]
    n = sum(b["n_pairs"] for b in measured)
    assert p["n_pairs"] == n
    m = p["rig"]["metric"]
    assert m["n"] == n and abs(m["ratio"] - 1 / 3) < 1e-12
    assert m["headline"] == (
        "Tokens per Solved Task: with 10.0k vs without 30.0k (-67%, 95% interval -67% to -67%)"
    )
    # Every pair agrees both ways: the guard is the pooled pass rate's Newcombe lower bound over
    # all n pairs (29 pairs: -11.7 pts), short of the -10-pt margin on pilots. No saving is
    # credited yet, and the verdict says so.
    assert m["guard"].startswith(f"Pass rate: {n} of {n} passed with vs {n} of {n} passed without")
    low = stats.paired_diff_ci(stats.PairCounts(n, 0, 0, 0))[1] * 100
    assert f"at worst {low:+.0f} pts" in m["guard"]
    assert low <= -rig_score.M["margin_pts"] and m["noninferior"] is False
    assert p["rig"]["verdict"]["id"] == "cant"
    assert any(g["id"] == "not_noninferior" for g in p["rig"]["gates"])


def test_a_suite_is_on_the_pass_rate_by_default(tmp_path: Path, monkeypatch):
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    wf = _starter(c, "Fix a bug")
    r = c.post("/api/lab/suite", json={"workflow": wf, "budget": 50}, headers=ORIGIN)
    v = _suite_wait(c, r.json()["job"])
    assert v["metric"] == "pass_rate" and "metric" not in v["pooled"]["rig"]
    assert c.post(
        "/api/lab/suite", json={"workflow": wf, "budget": 5, "metric": "vibes"}, headers=ORIGIN
    ).status_code == 422  # fmt: skip


def test_a_suite_on_the_pass_rate_runs_each_benchs_planned_pairs(tmp_path: Path, monkeypatch):
    # Every trial passes both ways: no bench is decided at 99%, which would have kept a single
    # run going. A suite's benches run their pilot, as the estimate prices it (suite.auto_extend).
    from proving_ground import bench as bench_mod

    assert suite.rule("auto_extend") is False
    c, _ = _lab_client(tmp_path, monkeypatch, lambda req: 1.0)
    wf = _starter(c, "Fix a bug")
    r = c.post("/api/lab/suite", json={"workflow": wf, "budget": 50}, headers=ORIGIN)
    v = _suite_wait(c, r.json()["job"])
    measured = [b for b in v["benches"] if b["n_pairs"]]
    assert v["status"] == "done" and len(measured) >= 2
    tasks = {b.id: len(b.scenarios) for b in bench_mod.benches()}
    for b in measured:
        assert b["n_pairs"] == tasks[b["bench"]]
        ev = c.get(f"/api/lab/runs/{b['bench']}/{b['experiment']}/events").text
        assert '"type": "extended"' not in ev and '"type": "settled"' not in ev
    assert v["pooled"]["n_pairs"] == sum(tasks[b["bench"]] for b in measured)
