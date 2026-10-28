"""Compare 2 to 4 workflows on one bench: the plan, the ranking rule, and the run loop."""

import math
import threading
import time
from pathlib import Path

import pytest

from proving_ground import compare
from proving_ground.compare import (
    StartError,
    align,
    align_candidates,
    drive,
    more_pairs,
    new_job,
    plan,
    rank,
)

# ---------- the plan: an even split, one baseline per session model ----------


def _item(i, model="sonnet", w=0.5, wo=0.25):
    return {"id": f"w{i}", "name": f"W{i}", "model": model, "with_usd": w, "without_usd": wo}


def test_plan_pays_the_baseline_once_per_model_and_splits_evenly():
    got = plan([_item(1), _item(2), _item(3, model="opus")], pairs=4, budget=12)
    a, b, c = got["workflows"]
    assert got["share"] == 4.0 and all(r["budget"] == 4.0 for r in got["workflows"])
    # The first pays both arms; the second (same model) reuses all four "without" trials.
    assert a["predicted_usd"] == 4 * 0.75 and a["shared_baseline"] == 0
    assert b["predicted_usd"] == 4 * 0.5 and b["shared_baseline"] == 4
    # Another session model can't share it: it pays its own.
    assert c["predicted_usd"] == 4 * 0.75 and c["shared_baseline"] == 0
    assert got["total_usd"] == 3 + 2 + 3 and got["baselines"] == 2
    assert all(r["pairs_in_budget"] == 4 for r in got["workflows"])


def test_plan_says_how_many_pairs_each_share_pays_for():
    # $2 each: the first pays 0.75 a pair (2 pairs), the second 0.5 a reused pair (4 pairs).
    a, b = plan([_item(1), _item(2)], pairs=4, budget=4)["workflows"]
    assert (a["pairs_in_budget"], a["predicted_in_budget"]) == (2, 1.5)
    # Only the two baseline pairs the first ran are there to reuse; the rest are paid for.
    assert b["shared_baseline"] == 2
    assert b["pairs_in_budget"] == 3  # 0.5 + 0.5 + 0.75 = 1.75; a fourth would be 2.5


# ---------- the ranking rule: no winner while the intervals overlap ----------


def _row(i, diff, lo, hi, n=10, rig=None, valid=True):
    return {
        "id": f"w{i}",
        "name": f"W{i}",
        "rig": rig,
        "diff": diff,
        "ci_low": lo,
        "ci_high": hi,
        "n_pairs": n,
        "valid": valid,
    }


def test_a_winner_only_when_its_interval_clears_every_other():
    got = rank([_row(1, 0.1, -0.1, 0.3, rig=40), _row(2, 0.6, 0.4, 0.8, rig=80)])
    assert got["state"] == "winner" and got["winner"] == "w2" and got["order"] == ["w2", "w1"]
    assert got["text"] == "W2 comes out ahead: its interval is clear of every other one's."


def test_overlapping_intervals_never_name_a_winner():
    rows = [_row(1, 0.5, 0.2, 0.8, rig=70), _row(2, 0.3, 0.0, 0.6, rig=55)]
    got = rank(rows)
    assert got["state"] == "not_proven" and got["winner"] is None
    assert got["close"] == ["w1", "w2"]
    # Half-widths 0.3 + 0.3 over a gap of 0.2 at 10 pairs: 10 * 3^2 = 90 pairs, 80 more.
    assert got["more_pairs"] == 80
    assert (
        got["text"] == "Not proven yet: can't tell W1 and W2 apart yet: about 80 more pairs each."
    )


def test_overlap_with_any_lower_one_is_enough_to_hold_back():
    # Ranked by Rig score: w3 is second but w2's interval is the one that reaches w1's.
    rows = [
        _row(1, 0.7, 0.5, 0.9, rig=90),
        _row(3, 0.2, 0.0, 0.4, rig=60),
        _row(2, 0.4, 0.1, 0.55, rig=50),
    ]
    got = rank(rows)
    assert got["winner"] is None and got["close"] == ["w1", "w2"]


def test_one_more_pair_is_said_in_the_singular():
    got = rank([_row(1, 0.5, 0.3, 0.7, n=20, rig=70), _row(2, 0.1, -0.1, 0.31, n=10, rig=40)])
    assert got["more_pairs"] == 1 and got["text"].endswith("about 1 more pair each.")


def test_level_results_say_more_pairs_may_never_separate_them():
    got = rank([_row(1, 0.3, 0.1, 0.5, rig=60), _row(2, 0.3, 0.1, 0.5, rig=60)])
    assert got["winner"] is None and got["more_pairs"] is None
    assert "more pairs may never separate them" in got["text"]


def test_a_huge_number_of_pairs_is_said_as_more_than_the_cap():
    got = rank([_row(1, 0.31, 0.0, 0.62, rig=60), _row(2, 0.3, 0.0, 0.6, rig=59)])
    cap = compare.rule("more_pairs_cap")
    assert got["more_pairs"] > cap and f"more than {cap} more pairs each" in got["text"]


def test_only_valid_measured_results_are_ranked():
    rows = [
        _row(1, 0.9, 0.8, 1.0, rig=95, valid=False),  # not evidence: never the winner
        _row(2, 0.3, 0.1, 0.5, rig=50),
        {
            "id": "w3",
            "name": "W3",
            "rig": None,
            "diff": None,
            "ci_low": None,
            "ci_high": None,
            "n_pairs": 0,
            "valid": True,
        },
    ]
    got = rank(rows)
    assert got["state"] == "too_few" and got["order"] == ["w2"] and got["winner"] is None


def test_more_pairs_uses_the_smaller_sample():
    a, b = _row(1, 0.5, 0.3, 0.7, n=20), _row(2, 0.1, -0.1, 0.3, n=10)
    # Half-widths 0.2 + 0.2 over a gap of 0.4: already apart at 10 pairs -> at least 1 more.
    assert more_pairs(a, b) == 1


# ---------- across session models: rank by the pass rate with it, not the lift ----------


def _on(i, model, pass_with, pass_without, rig, n=20, cost=0.5):
    d = pass_with - pass_without
    return _row(i, d, d - 0.15, d + 0.15, n=n, rig=rig) | {
        "model": model,
        "pass_with": pass_with,
        "cost": cost,
    }


def test_across_models_a_strong_model_already_passing_beats_a_weak_one_with_a_big_lift():
    weak = _on(1, "claude-haiku-5-5", 0.5, 0.1, rig=85)  # +40 points, from 10% to 50%
    strong = _on(2, "claude-opus-5-5", 0.95, 0.9, rig=40)  # +5 points, but ends at 95%
    # On one model the lift-heavy Rig score would put the weak one first.
    assert rank([weak | {"model": "m"}, strong | {"model": "m"}])["order"] == ["w1", "w2"]
    got = rank([weak, strong])
    assert got["by"] == "pass_with" and got["order"] == ["w2", "w1"]
    assert got["models"] == ["claude-haiku-5-5", "claude-opus-5-5"]
    assert got["by_text"].startswith(
        "They ran on 2 models, so each lift is against its own model's baseline; ranked by"
    )
    # Wilson at 19/20 is about 76% to 99%, at 10/20 about 30% to 70%: apart, so a winner.
    hi, lo = got["ranked"]["w2"], got["ranked"]["w1"]
    assert hi["value"] == 0.95 and 0.75 < hi["lo"] < 0.77 and 0.69 < lo["hi"] < 0.71
    assert got["state"] == "winner" and got["winner"] == "w2"
    assert (
        got["text"] == "W2 comes out ahead: its pass rate's interval is clear of every other one's."
    )
    # Each lift is still shown, against its own baseline.
    named = rank([weak, strong], label=lambda m: m.split("-")[1].title())
    assert named["lift_vs"] == {"w1": "vs Direct on Haiku", "w2": "vs Direct on Opus"}


def test_across_models_the_winner_rule_holds_on_pass_rate_intervals():
    # Rig scores and lifts far apart, pass rates close: no winner, and the pairs gap is in pass rate.
    a = _on(1, "claude-sonnet-5-5", 0.8, 0.3, rig=90, n=10)
    b = _on(2, "claude-opus-5-5", 0.7, 0.65, rig=30, n=10)
    got = rank([b, a])
    assert got["order"] == ["w1", "w2"] and got["winner"] is None
    assert got["state"] == "not_proven" and got["close"] == ["w1", "w2"]
    ga, gb = got["ranked"]["w1"], got["ranked"]["w2"]
    h = (ga["hi"] - ga["lo"]) / 2 + (gb["hi"] - gb["lo"]) / 2
    assert got["more_pairs"] == max(1, math.ceil(10 * (h / 0.1) ** 2 - 1e-9) - 10)


def test_across_models_equal_pass_rates_go_to_the_cheaper_one():
    dear = _on(1, "claude-opus-5-5", 0.8, 0.7, rig=60, cost=1.2)
    cheap = _on(2, "claude-haiku-5-5", 0.8, 0.2, rig=50, cost=0.3)
    unpriced = _on(3, "claude-sonnet-5-5", 0.8, 0.5, rig=99, cost=None)
    assert rank([dear, unpriced, cheap])["order"] == ["w2", "w1", "w3"]


def test_on_one_model_the_ranking_is_unchanged():
    a = _on(1, "claude-sonnet-5-5", 0.5, 0.1, rig=85)
    b = _on(2, "claude-sonnet-5-5", 0.95, 0.9, rig=40)
    got = rank([b, a])
    assert got["by"] == "rig" and got["by_text"] == "Ranked by Rig score" and got["lift_vs"] == {}
    assert got["order"] == ["w1", "w2"] and got["ranked"]["w1"]["value"] == pytest.approx(0.4)


# ---------- before a run: offer to put them all on one model ----------


def test_align_offers_the_most_common_model_and_says_what_the_extra_baseline_costs():
    items = [_item(1), _item(2), _item(3, model="opus", w=0.8, wo=0.4)]
    now = plan(items, pairs=4, budget=100)
    assert now["baselines"] == 2 and align_candidates([i["model"] for i in items]) == ["sonnet"]
    on_sonnet = plan([_item(i) for i in (1, 2, 3)], pairs=4, budget=100)
    got = align(now, {"sonnet": on_sonnet}, label=lambda m: m.title())
    # The opus one paid 4 x 0.4 for its own baseline; all on sonnet reuse the first one's.
    assert got["model"] == "sonnet" and got["extra_baseline_usd"] == 1.6
    assert got["notice"] == "2 models, so 2 baselines: +$1.60."
    assert got["action"] == "Run All on Sonnet"
    # Now 3.0 + 2.0 + 4.8 = 9.8; all on sonnet 3.0 + 2.0 + 2.0 = 7.0.
    assert now["total_usd"] == 9.8 and got["total_usd"] == 7.0 and got["saving_usd"] == 2.8
    assert got["result"] == "one shared baseline, ≈ $7.00 in total, saving $2.80."


def test_align_breaks_a_tie_on_the_cheaper_model_and_says_when_it_costs_more():
    items = [_item(1, model="opus", w=1.0, wo=0.5), _item(2, model="haiku", w=0.2, wo=0.1)]
    now = plan(items, pairs=2, budget=100)
    assert align_candidates(["opus", "haiku"]) == ["opus", "haiku"]
    priced = {
        "opus": plan([_item(i, model="opus", w=1.0, wo=0.5) for i in (1, 2)], 2, 100),
        "haiku": plan([_item(i, model="haiku", w=0.2, wo=0.1) for i in (1, 2)], 2, 100),
    }
    assert align(now, priced)["model"] == "haiku"
    # Only opus on offer (say, the most common one): it costs more, and it says so.
    more = align(now, {"opus": priced["opus"]})
    assert more["saving_usd"] < 0 and "more since opus costs more per trial" in more["result"]


def test_align_is_nothing_when_one_baseline_is_shared():
    now = plan([_item(1), _item(2)], pairs=2, budget=10)
    assert align(now, {"sonnet": now}) is None


# ---------- the run loop, with a fake runner ----------


class FakeRuns:
    """Each start() makes a run that finishes after `ticks` polls, spending its budget's half."""

    def __init__(self, ticks=2, fail=()):
        self.started: list[tuple[str, float]] = []
        self.left: dict[int, int] = {}
        self.cost: dict[int, float] = {}
        self.stopped: list[int] = []
        self.ticks, self.fail = ticks, set(fail)
        self.on_start = None

    def start(self, wf, budget):
        if wf["id"] in self.fail:
            raise StartError(f"{wf['name']} won't compile")
        eid = len(self.started) + 1
        self.started.append((wf["id"], budget))
        self.left[eid] = self.ticks
        self.cost[eid] = budget / 2
        if self.on_start:
            self.on_start(eid)
        return eid

    def finished(self, eid):
        self.left[eid] -= 1
        return self.left[eid] < 0

    def stop(self, eid):
        self.stopped.append(eid)
        self.left[eid] = 0


def _job(n=3, budget=9.0):
    wfs = [{"id": f"w{i}", "name": f"W{i}", "steps": []} for i in range(1, n + 1)]
    return new_job("qa", "QA", "claude-code", budget, "pilot", wfs)


def _drive(job, f):
    drive(job, f.start, f.finished, lambda eid: f.cost[eid], f.stop, sleep=lambda s: None)


def test_runs_each_in_pinned_order_with_an_even_share():
    job, f = _job(), FakeRuns()
    _drive(job, f)
    assert [w for w, _ in f.started] == ["w1", "w2", "w3"]
    assert [b for _, b in f.started] == [3.0, 3.0, 3.0]
    assert job.status == "done"
    assert [r["status"] for r in job.rows] == ["done"] * 3
    assert [r["experiment"] for r in job.rows] == [1, 2, 3]
    assert [r["spent"] for r in job.rows] == [1.5, 1.5, 1.5]


def test_a_workflow_that_cant_start_is_marked_and_the_rest_still_run():
    job, f = _job(), FakeRuns(fail={"w2"})
    _drive(job, f)
    assert [r["status"] for r in job.rows] == ["done", "error", "done"]
    assert job.rows[1]["detail"] == "W2 won't compile" and job.rows[1]["experiment"] is None
    assert job.rows[2]["budget"] == 3.0  # still its even share, not what w2 left


def test_stop_ends_the_run_in_progress_and_skips_the_rest():
    job, f = _job(), FakeRuns(ticks=5)
    f.on_start = lambda eid: job.stop.set() if eid == 2 else None
    _drive(job, f)
    assert f.stopped and set(f.stopped) == {2}
    assert [r["status"] for r in job.rows] == ["done", "stopped", "skipped"]
    assert job.rows[2]["experiment"] is None and job.status == "stopped"


def test_two_to_four_distinct_workflows():
    with pytest.raises(ValueError, match="2 to 4"):
        _job(n=1)
    with pytest.raises(ValueError, match="2 to 4"):
        _job(n=5)
    w = {"id": "same", "name": "S", "steps": []}
    with pytest.raises(ValueError, match="twice"):
        new_job("qa", "QA", "claude-code", 5, "pilot", [w, w])


# ---------- through the API: one bench, one shared baseline ----------


def _client(tmp_path, monkeypatch, env=None):
    from test_bench import _lab_client

    return _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0, env=env)


def _starters(c, *names):
    from test_bench import _starter

    return [_starter(c, n) for n in names]


def _wait(c, job, done=("done", "stopped")):
    for _ in range(600):
        v = c.get(f"/api/lab/compare/{job}").json()
        if v["status"] in done:
            return v
        time.sleep(0.05)
    raise AssertionError("comparison did not finish")


def test_measure_the_set_on_one_bench_with_one_baseline(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN

    c, calls = _client(tmp_path, monkeypatch)
    a, b = _starters(c, "Fix a bug", "Refactor safely")
    body = {"workflows": [a, b], "bench": "qa", "budget": 10}
    # Priced first, with the second one's baseline counted as reused.
    p = c.post("/api/lab/compare/plan", json=body, headers=ORIGIN).json()
    one, two = p["workflows"]
    assert p["share"] == 5.0 and one["shared_baseline"] == 0 and two["shared_baseline"] > 0
    assert two["predicted_usd"] < one["predicted_usd"]
    assert p["total_usd"] == round(one["predicted_usd"] + two["predicted_usd"], 4)
    # What "Full" buys at $10, priced on the pilot too: the workflow its share pays least for.
    from proving_ground.budget import full_size

    full = c.post("/api/lab/compare/plan", json=body | {"size": "full"}, headers=ORIGIN).json()
    least = min(w["pairs_in_budget"] for w in full["workflows"])
    assert p["full"] == full["full"] == full_size(least, full["pairs"], p["pairs"])
    assert p["full"]["text"].startswith("Full · ") and "conclusive" not in p["full"]["text"]

    r = c.post("/api/lab/compare", json=body, headers=ORIGIN)
    assert r.status_code == 200, r.text
    v = _wait(c, r.json()["job"])
    assert v["status"] == "done"
    rows = v["workflows"]
    assert [x["id"] for x in rows] == [a["id"], b["id"]]
    assert [x["budget"] for x in rows] == [5.0, 5.0]
    assert all(x["result"] and x["result"]["n_pairs"] > 0 for x in rows)
    # The second workflow reused every "without" trial the first ran: one baseline paid for.
    assert rows[1]["result"]["reused"] == rows[0]["result"]["n_pairs"]
    without = [q for q in calls if q.agent != "nop" and not q.skills]
    assert len(without) == rows[0]["result"]["n_pairs"]
    # The fake helps both equally: their intervals overlap, so no winner is named.
    assert v["rank"]["winner"] is None and v["rank"]["state"] == "not_proven"
    assert v["rank"]["text"].startswith("Not proven yet: can't tell ")
    # The same standing afterwards, from each one's latest valid result.
    s = c.post(
        "/api/lab/compare/standing",
        json={
            "bench": "qa",
            "workflows": [{"id": a["id"], "name": a["name"]}, {"id": b["id"], "name": b["name"]}],
        },
        headers=ORIGIN,
    ).json()
    assert [x["result"]["id"] for x in s["workflows"]] == [x["experiment"] for x in rows]
    assert s["rank"]["state"] == v["rank"]["state"]


def test_measuring_the_set_needs_a_sign_in(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN

    c, _ = _client(tmp_path, monkeypatch, env={"NOTHING": "1"})
    a, b = _starters(c, "Fix a bug", "Refactor safely")
    body = {"workflows": [a, b], "bench": "qa", "budget": 10}
    assert c.post("/api/lab/compare/plan", json=body, headers=ORIGIN).status_code == 200
    r = c.post("/api/lab/compare", json=body, headers=ORIGIN)
    assert r.status_code == 400 and "Sign in" in r.json()["detail"]


def test_a_set_out_of_range_is_refused(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN

    c, _ = _client(tmp_path, monkeypatch)
    (a,) = _starters(c, "Fix a bug")
    for wfs in ([a], [a, a]):
        r = c.post("/api/lab/compare", json={"workflows": wfs, "bench": "qa"}, headers=ORIGIN)
        assert r.status_code == 422


def test_stop_the_set_and_nothing_else_starts_meanwhile(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN

    import proving_ground.runner.harbor as harbor

    c, _ = _client(tmp_path, monkeypatch)
    inner, gate, entered = harbor.harbor_executor, threading.Event(), threading.Event()

    def slow(req):
        entered.set()
        gate.wait(5)
        return inner(req)

    monkeypatch.setattr(harbor, "harbor_executor", slow)
    a, b, d = _starters(c, "Fix a bug", "Refactor safely", "Build a feature")
    job = c.post(
        "/api/lab/compare",
        json={"workflows": [a, b, d], "bench": "qa", "budget": 9},
        headers=ORIGIN,
    ).json()["job"]
    assert entered.wait(5)
    one = {"workflow": a, "bench": "qa"}
    assert c.post("/api/lab/run", json=one, headers=ORIGIN).status_code == 409
    again = {"workflows": [a, b], "bench": "qa"}
    assert c.post("/api/lab/compare", json=again, headers=ORIGIN).status_code == 409
    assert c.post(f"/api/lab/compare/{job}/stop", headers=ORIGIN).status_code == 200
    gate.set()
    v = _wait(c, job)
    assert v["status"] == "stopped"
    assert [x["status"] for x in v["workflows"]] == ["stopped", "skipped", "skipped"]
    assert c.post(f"/api/lab/compare/{job}/stop", headers=ORIGIN).status_code == 404


def _on_model(wf, model):
    """The workflow with its main steps (the "do" ones) on `model`: its session model."""
    return wf | {
        "steps": [st | {"model": model} if st["kind"] == "do" else st for st in wf["steps"]]
    }


def test_plan_on_two_models_prices_running_all_on_one(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN

    c, _ = _client(tmp_path, monkeypatch)
    a, b = _starters(c, "Fix a bug", "Refactor safely")
    b = _on_model(b, "claude-opus-5-5")
    body = {"workflows": [a, b], "bench": "qa", "budget": 50}
    p = c.post("/api/lab/compare/plan", json=body, headers=ORIGIN).json()
    assert p["baselines"] == 2 and [w["model"] for w in p["workflows"]] == [
        "claude-sonnet-5-5",
        "claude-opus-5-5",
    ]
    al = p["align"]
    # One each: a tie, so the cheaper model (workflow-patterns: Sonnet costs 3, Opus 5).
    assert al["model"] == "claude-sonnet-5-5" and al["action"] == "Run All on Sonnet 5.5"
    assert al["extra_baseline_usd"] == p["workflows"][1]["baseline_usd"] > 0
    assert al["notice"] == f"2 models, so 2 baselines: +${al['extra_baseline_usd']:,.2f}."
    assert al["saving_usd"] > 0
    # Done as offered: one baseline, and the plan is what was promised.
    after = c.post(
        "/api/lab/compare/plan",
        json=body | {"workflows": [a, _on_model(b, "claude-sonnet-5-5")]},
        headers=ORIGIN,
    ).json()
    assert after["baselines"] == 1 and after["align"] is None
    assert after["total_usd"] == al["total_usd"]
    assert round(p["total_usd"] - after["total_usd"], 4) == al["saving_usd"]


def test_a_set_measured_on_two_models_is_ranked_by_pass_rate(tmp_path: Path, monkeypatch):
    from test_api_workspace import ORIGIN

    c, _ = _client(tmp_path, monkeypatch)
    a, b = _starters(c, "Fix a bug", "Refactor safely")
    b = _on_model(b, "claude-opus-5-5")
    r = c.post(
        "/api/lab/compare", json={"workflows": [a, b], "bench": "qa", "budget": 20}, headers=ORIGIN
    )
    assert r.status_code == 200, r.text
    v = _wait(c, r.json()["job"])
    rows = v["workflows"]
    assert [x["result"]["model"] for x in rows] == ["claude-sonnet-5-5", "claude-opus-5-5"]
    # Two baselines: the second ran its own "without" trials, none reused.
    assert rows[1]["result"]["reused"] == 0
    assert all(x["result"]["cost_with"] is not None for x in rows)
    rk = v["rank"]
    assert rk["by"] == "pass_with" and rk["models"] == ["claude-sonnet-5-5", "claude-opus-5-5"]
    # The fake passes every "with" trial: level on pass rate, so never a winner.
    assert {k: g["value"] for k, g in rk["ranked"].items()} == {a["id"]: 1.0, b["id"]: 1.0}
    assert rk["winner"] is None and "more pairs may never separate them" in rk["text"]
    assert rk["lift_vs"] == {a["id"]: "vs Direct on Sonnet 5.5", b["id"]: "vs Direct on Opus 5.5"}
    assert [x["model"] for x in rows] == ["claude-sonnet-5-5", "claude-opus-5-5"]


def _standing(c, wfs):
    from test_api_workspace import ORIGIN

    r = c.post("/api/lab/compare/standing", json={"bench": "qa", "workflows": wfs}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()


def test_after_run_all_on_one_model_a_result_on_the_old_one_is_marked_and_not_ranked(
    tmp_path: Path, monkeypatch
):
    from test_api_workspace import ORIGIN

    c, _ = _client(tmp_path, monkeypatch)
    a, b = _starters(c, "Fix a bug", "Refactor safely")
    on_opus = _on_model(b, "claude-opus-5-5")
    body = {"workflows": [a, on_opus], "bench": "qa", "budget": 20}
    v = _wait(c, c.post("/api/lab/compare", json=body, headers=ORIGIN).json()["job"])
    assert v["rank"]["by"] == "pass_with" and len(v["rank"]["order"]) == 2

    # Still on Opus: its own result, ranked across the two models as before.
    s = _standing(c, [a, on_opus])
    assert s["models"] == {a["id"]: "claude-sonnet-5-5", b["id"]: "claude-opus-5-5"}
    assert all(x["result"]["other_model"] is None for x in s["workflows"])
    assert s["rank"]["order"] == v["rank"]["order"]

    # Run all on Sonnet: the Opus result is not this workflow's any more. Shown marked, not ranked.
    s = _standing(c, [a, _on_model(on_opus, "claude-sonnet-5-5")])
    one, two = s["workflows"]
    assert one["result"]["other_model"] is None
    assert two["result"]["model"] == "claude-opus-5-5"
    assert two["result"]["other_model"] == {
        "model": "claude-opus-5-5",
        "label": "Opus 5.5",
        "text": "On Opus 5.5, not this one: not ranked. Measure it again to rank it.",
    }
    assert s["rank"]["order"] == [a["id"]] and s["rank"]["state"] == "too_few"
    assert s["rank"]["by"] == "rig"  # one model left among the ranked: today's ranking

    # Measured again on Sonnet: that one is its result now, on one model with one baseline.
    v2 = _wait(
        c,
        c.post(
            "/api/lab/compare",
            json=body | {"workflows": [a, _on_model(on_opus, "claude-sonnet-5-5")]},
            headers=ORIGIN,
        ).json()["job"],
    )
    s = _standing(c, [a, _on_model(on_opus, "claude-sonnet-5-5")])
    assert [x["result"]["model"] for x in s["workflows"]] == ["claude-sonnet-5-5"] * 2
    assert s["workflows"][1]["result"]["id"] == v2["workflows"][1]["experiment"]
    assert s["rank"]["by"] == "rig" and len(s["rank"]["order"]) == 2
    # Ids and names alone (no steps): every model counts, as before.
    plain = _standing(c, [{"id": w["id"], "name": w["name"]} for w in (a, b)])
    assert plain["models"] == {} and all(
        x["result"]["other_model"] is None for x in plain["workflows"]
    )
