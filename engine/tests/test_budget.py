"""The budget is a cap (trial-budget): nothing starts that it can't pay for."""

import json
import random
import tempfile
import threading
from dataclasses import replace
from pathlib import Path

from test_harbor_runner import Recorder, result, runner, spec

from proving_ground import skills
from proving_ground.budget import CostModel, Ledger, cant_start, history, prior_usd
from proving_ground.models import Scenario, Treatment, TreatmentKind
from proving_ground.runner.base import TrialSpec
from proving_ground.runner.fake import FakeRunner
from proving_ground.runner.harbor import TrialRequest, _agent_kwargs
from proving_ground.scheduler import run_experiment
from proving_ground.store import Store
from proving_ground.trial import TrialOutcome

B = skills.load("trial-budget").values
TREAT = Treatment(kind=TreatmentKind.SKILL, name="wf", path="/x", content_hash="b" * 64)
SONNET = "claude-sonnet-5-5"


def sc(sid):
    return Scenario(id=sid, instruction="do it", check="exit 0", check_status="approved")


def priced(costs):
    """A decide() that charges each arm its next cost from `costs[arm]`."""
    left = {arm: list(c) for arm, c in costs.items()}

    def decide(s: TrialSpec) -> TrialOutcome:
        return TrialOutcome(
            s.scenario.id, s.scenario.kind, s.arm, s.repeat, "pass", cost_usd=left[s.arm].pop(0)
        )

    return decide


def run(runner, scenarios, repeats, budget, store=None, model=SONNET, cost_model=None):
    store = store or Store("sqlite://")
    pid = store.ensure_project("/repo")
    eid = store.create_experiment(pid, TREAT, model, repeats=repeats, budget_usd=budget, seed=1)
    events: list[dict] = []
    run_experiment(
        store,
        runner,
        eid,
        scenarios,
        TREAT,
        Path("/repo"),
        model,
        1,
        repeats,
        budget,
        on_event=events.append,
        cost_model=cost_model,
    )
    return store, eid, events


def stop_event(events):
    return next(e for e in events if e["type"] == "stopped_budget")


# ---------- the real run: $2.00 budget, ended at $2.90 ----------

# Experiment 1 on the bugfix bench, Claude Code + Sonnet 5.5, a handed-over workflow, $2.00:
# with 0.971, without 0.029, with 0.937, without 0.044, then a fifth trial (with, 0.922) started
# at $1.98 spent and ended the run at $2.90.
REAL = {"with": [0.971, 0.937, 0.922, 0.95], "without": [0.029, 0.044, 0.03, 0.03]}
BUGFIX = [sc("bulk-threshold"), sc("coupon-case"), sc("delete-the-test")]


def test_the_real_overshoot_now_stops_within_the_budget():
    r = FakeRunner(priced(REAL))
    store, eid, events = run(r, BUGFIX, 1, 2.0)
    assert store.spent(eid) <= 2.0
    assert round(store.spent(eid), 3) == 1.0  # one whole pair; the second isn't started
    assert len(r.calls) == 2
    e = stop_event(events)
    # Second pair: with 0.971 x 1.25 + without 0.029 x 1.25 = $1.25, and $1.00 is left.
    assert e["predicted_usd"] == 1.25 and e["left_usd"] == 1.0
    assert (
        e["reason"] == "the next pair would cost about $1.25 (from this run's trials); $1.00 left"
    )
    assert store.get_experiment(eid).status == "stopped_budget"


def test_the_reported_case_140_trials_on_2_dollars():
    r = FakeRunner(priced({"with": [1.40] * 3, "without": [0.05] * 3}))
    store, eid, events = run(r, BUGFIX, 1, 2.0)
    assert round(store.spent(eid), 2) == 1.45 <= 2.0
    assert stop_event(events)["reason"].startswith("the next pair would cost about $1.81")


# ---------- never start a pair that would go over ----------


def test_never_starts_a_pair_that_would_exceed_the_budget():
    rng = random.Random(7)
    for _ in range(200):
        budget = rng.uniform(0.5, 6.0)
        flat = {"with": rng.uniform(0.05, 1.0), "without": rng.uniform(0.01, 0.25)}
        # Every trial costs what the prior predicts or less, so no prediction is too low.
        costs = {a: [flat[a]] * 40 for a in flat}
        r = FakeRunner(priced(costs))
        store, eid, events = run(r, [sc("a"), sc("b")], 10, budget)
        assert store.spent(eid) <= budget + 1e-9
        # Pairs only: never one arm of a pair without the other.
        keys = {(c.scenario.id, c.repeat) for c in r.calls}
        assert len(r.calls) == 2 * len(keys)
        if events[-1]["type"] == "stopped_budget":
            e = events[-1]
            assert e["spent_usd"] + e["predicted_usd"] > budget  # it stopped only when it had to


def test_a_dear_first_arm_stops_the_pair_before_its_second():
    # The prior says $1.25 + $0.31 for the pair; the "with" trial costs $1.90 of $2.
    r = FakeRunner(priced({"with": [1.90], "without": [0.03]}))
    store, eid, events = run(r, [sc("a")], 1, 2.0)
    assert [c.arm for c in r.calls] == ["with"]
    e = stop_event(events)
    assert e["reason"] == (
        "the 'without' trial would cost about $0.31; $0.10 left after the trial before it cost "
        "more than predicted"
    )


def test_bounded_worst_case_without_an_in_trial_cap():
    # An agent that can't stop itself: a trial that costs far more than predicted overshoots by
    # what it cost beyond what was free when it started, once. Nothing starts after it.
    r = FakeRunner(priced({"with": [3.0, 1.0], "without": [0.03, 0.03]}))
    store, eid, _ = run(r, [sc("a"), sc("b")], 1, 2.0)
    assert len(r.calls) == 1
    assert store.spent(eid) == 3.0  # $1.00 over: $3.00 cost against the $2.00 free at its start


def test_with_an_in_trial_cap_the_budget_holds_even_when_the_prediction_is_wrong():
    rng = random.Random(11)
    for _ in range(200):
        budget = rng.uniform(0.5, 6.0)
        costs = {a: [rng.uniform(0.0, 4.0) for _ in range(40)] for a in ("with", "without")}
        r = FakeRunner(priced(costs), caps_cost=True)
        store, eid, _ = run(r, [sc("a"), sc("b")], 10, budget)
        assert store.spent(eid) <= budget + 1e-9
        for c in r.calls:
            assert c.max_cost_usd is not None and c.max_cost_usd > 0


def test_the_cap_is_the_trials_reservation_plus_what_is_free():
    r = FakeRunner(priced({"with": [3.0], "without": [0.03]}), caps_cost=True)
    store, eid, _ = run(r, [sc("a")], 1, 2.0)
    with_cap = r.calls[0].max_cost_usd
    # $2 less the "without" arm's reservation ($0.25 x 1.25): the "with" trial may use the rest.
    assert round(with_cap, 4) == round(2.0 - B["prior_usd"]["without"] * B["margin"], 4)
    t = store.trials(eid)
    assert t[0].outcome == "errored" and t[0].cost_usd == with_cap  # cut short, not a fail
    assert store.spent(eid) <= 2.0


# ---------- predictions ----------


def test_first_pair_with_nothing_measured_uses_the_prior():
    pair = sum(prior_usd(SONNET).values()) * B["margin"]
    assert round(pair, 4) == round((1.00 + 0.25) * 1.25, 4)
    r = FakeRunner(priced({"with": [0.5], "without": [0.05]}))
    store, eid, events = run(r, [sc("a")], 1, pair - 0.01)
    assert r.calls == []
    assert stop_event(events)["reason"] == (
        f"the next pair would cost about ${pair:.2f} (a first guess: nothing measured yet); "
        f"${pair - 0.01:.2f} left"
    )
    r2 = FakeRunner(priced({"with": [0.5], "without": [0.05]}))
    store, eid, events = run(r2, [sc("a")], 1, pair)
    assert len(r2.calls) == 2 and events[-1]["type"] == "done"


def test_prior_scales_with_the_model_and_a_local_model_is_free():
    assert (
        prior_usd("claude-opus-5-5")["with"]
        > prior_usd(SONNET)["with"]
        > prior_usd("claude-haiku-5-5")["with"]
    )
    assert prior_usd("gpt-something") == prior_usd(SONNET)
    assert CostModel(prior_usd(SONNET), free=True).estimate("with", [5.0]) == (0.0, "a local model")
    r = FakeRunner(priced({"with": [0.0] * 2, "without": [0.0] * 2}), free=True)
    _, _, events = run(r, [sc("a")], 2, 0.01)
    assert events[-1]["type"] == "done" and len(r.calls) == 4


def test_mean_or_max_and_never_below_the_dearest():
    here = "from this run's trials"
    m = CostModel({"with": 9.0, "without": 9.0})
    assert m.estimate("with", [1.0, 3.0]) == (3.0, here)  # mean 2 x 1.25 = 2.5, under the 3
    got, src = m.estimate("with", [1.0, 1.2])
    assert abs(got - 1.1 * 1.25) < 1e-9 and src == here
    by_max = CostModel({"with": 9.0, "without": 9.0}, predict="max")
    assert by_max.estimate("with", [1.0, 2.0]) == (2.5, here)


def test_earlier_runs_on_the_bench_stand_in_before_the_prior(tmp_path):
    store = Store("sqlite://")
    pid = store.ensure_project(str(tmp_path))
    old = store.create_experiment(pid, TREAT, SONNET, repeats=1, budget_usd=5, seed=0)
    store.record_trial(old, TrialOutcome("a", sc("a").kind, "with", 0, "pass", cost_usd=0.2))
    store.record_trial(old, TrialOutcome("a", sc("a").kind, "without", 0, "pass", cost_usd=0.02))
    other = store.create_experiment(pid, TREAT, "claude-opus-5-5", repeats=1, budget_usd=5, seed=0)
    store.record_trial(other, TrialOutcome("a", sc("a").kind, "with", 0, "pass", cost_usd=9.0))
    new = store.create_experiment(pid, TREAT, SONNET, repeats=1, budget_usd=5, seed=0)
    h = history(store, tmp_path, new, SONNET, "claude-code")
    assert h == {"with": [0.2], "without": [0.02]}  # the Opus run says nothing about Sonnet
    assert history(store, tmp_path, new, SONNET, "codex") == {"with": [], "without": []}
    m = CostModel(prior_usd(SONNET), h)
    assert m.estimate("with", []) == (0.25, "measured on 1 earlier trial")


# ---------- before a run: measured costs, what it can detect, what it would take ----------


def _bench_with_runs(tmp_path):
    """A bench with an invalid run (the workflow never opened: still real costs), an errored and a
    zero-cost trial, and a run on Opus."""
    store = Store("sqlite://")
    pid = store.ensure_project(str(tmp_path))
    old = store.create_experiment(pid, TREAT, SONNET, repeats=3, budget_usd=5, seed=0)
    k = sc("a").kind
    for rep, (w, wo) in enumerate([(0.97, 0.03), (0.94, 0.04), (0.92, 0.035)]):
        store.record_trial(old, TrialOutcome("a", k, "with", rep, "pass", cost_usd=w))
        store.record_trial(old, TrialOutcome("a", k, "without", rep, "fail", cost_usd=wo))
    store.record_trial(old, TrialOutcome("b", k, "with", 0, "errored", cost_usd=4.0))
    store.record_trial(old, TrialOutcome("b", k, "without", 0, "pass", cost_usd=0.0))
    opus = store.create_experiment(pid, TREAT, "claude-opus-5-5", repeats=1, budget_usd=5, seed=0)
    store.record_trial(opus, TrialOutcome("a", k, "with", 0, "pass", cost_usd=1.5))
    return store, pid


def test_measured_costs_count_any_run_but_not_errored_or_unpriced_trials(tmp_path):
    from proving_ground.budget import measured

    store, pid = _bench_with_runs(tmp_path)
    seen, notes = measured(store, tmp_path, pid, SONNET, "claude-code", "wf")
    # Validity never enters: these costs are real even if the run says nothing about lift.
    assert seen == {"with": [0.97, 0.94, 0.92], "without": [0.03, 0.04, 0.035]} and notes == {}
    m = CostModel(prior_usd(SONNET), seen, notes=notes)
    got, src = m.estimate("with", [])
    assert src == "measured on 3 earlier trials"
    assert abs(got - max((0.97 + 0.94 + 0.92) / 3 * B["margin"], 0.97)) < 1e-9
    # Nothing on Haiku: the other models' trials, scaled by relative cost, and it says so.
    haiku, said = measured(store, tmp_path, pid, "claude-haiku-5-5", "claude-code", "wf")
    assert haiku["with"] == [c / 5 for c in [1.5]] + [c / 3 for c in [0.97, 0.94, 0.92]]
    assert said["with"] == "on Opus 5.5 and Sonnet 5.5, scaled to Haiku 5.5 by relative cost"
    src = CostModel(prior_usd("claude-haiku-5-5"), haiku, notes=said).estimate("without", [])[1]
    assert src == (
        "measured on 3 earlier trials on Sonnet 5.5, scaled to Haiku 5.5 by relative cost"
    )
    # Another agent: nothing measured, so the prior, and it says so.
    none, _ = measured(store, tmp_path, pid, SONNET, "codex", "wf")
    assert CostModel(prior_usd(SONNET), none).estimate("with", [])[1].startswith("a first guess")


def test_the_estimate_says_what_it_takes_to_detect_the_target_and_the_budget_for_it():
    from proving_ground.budget import budget_for, detectable_pts, forecast
    from proving_ground.stats import noise_half_width, pairs_for_half_width

    target = B["detect_target_pts"]
    need = pairs_for_half_width(target / 100, B["detect_base_rate"])
    # The fewest pairs whose half-width is the target: one fewer can't tell it from noise.
    assert noise_half_width(need, 0.5) <= target / 100 < noise_half_width(need - 1, 0.5)
    m = CostModel({"with": 0.95, "without": 0.04}, margin=1.0)
    f = forecast(m, 21, budget=5.0, pilot_pairs=3)
    assert f["sizing"] == {
        "target_pts": target,
        "pairs": need,
        "usd": budget_for(need, 0.99),
        "planned_pairs": 21,
        "planned_pts": detectable_pts(21),
        "enough_planned": False,
        "enough_budget": False,
    }
    # Rounded up to the budget field's step, and enough to pay for every one of those pairs.
    step = B["budget_step_usd"]
    assert f["sizing"]["usd"] % step == 0 and f["sizing"]["usd"] >= need * 0.99
    assert f["sizing"]["usd"] - step < need * 0.99
    # At $5 the full run stops after 5 pairs: no better than a 5-pair pilot, said plainly.
    assert f["pairs_in_budget"] == 5
    assert forecast(m, 21, 5.0, pilot_pairs=5)["no_better_than_pilot"] == (
        "At $5.00 this full run stops after 5 pairs: no more conclusive than the pilot."
    )
    assert f["no_better_than_pilot"] is None  # 5 pairs beat a 3-pair pilot
    assert forecast(m, 21, 50.0, pilot_pairs=3)["no_better_than_pilot"] is None
    assert forecast(m, 3, 5.0, pilot_pairs=3)["no_better_than_pilot"] is None  # the pilot itself
    # Set to that budget, a big enough run reaches the target.
    big = forecast(m, need, f["sizing"]["usd"])
    assert big["pairs_in_budget"] == need and big["sizing"]["enough_budget"]
    assert big["detect"]["pts"] <= target
    # A local model costs nothing: pairs still needed, no dollar amount.
    assert forecast(CostModel(prior_usd(SONNET), free=True), 4)["sizing"]["usd"] is None


def test_statuses_are_said_in_words():
    from proving_ground.budget import status_text
    from proving_ground.store import STATUSES

    assert status_text("stopped_budget") == "Stopped at the budget"
    assert status_text("stopped") == "Stopped" and status_text("done") == "Done"
    assert status_text("failed_preflight").startswith("Couldn't start: ")
    for st in STATUSES:  # every status the store can hold has its words
        assert "_" not in status_text(st) and st in B["status_words"]


# ---------- reservations: trials in flight can't spend the same dollars ----------


def _race(threads: int) -> tuple[Ledger, list[float]]:
    """`threads` pairs start at once against $2; each arm stops at its cap, as Claude Code does."""
    ledger, started, lock = Ledger(2.0), [], threading.Lock()
    go = threading.Barrier(threads)

    def pair() -> None:
        go.wait()
        got = ledger.reserve([0.3, 0.05])  # a pair: both arms or neither
        if got is None:
            return
        for res in got:
            cap = ledger.claim(res)
            with lock:
                started.append(cap)
            ledger.settle(res, random.uniform(0, cap))

    workers = [threading.Thread(target=pair) for _ in range(threads)]
    for t in workers:
        t.start()
    for t in workers:
        t.join()
    return ledger, started


def test_reservations_hold_under_concurrency():
    for _ in range(50):
        ledger, started = _race(16)
        assert ledger.reserved < 1e-9
        assert ledger.spent <= 2.0 + 1e-9
        assert 2 <= len(started) <= 2 * 5 and len(started) % 2 == 0  # at most 5 pairs of $0.35


def test_an_in_flight_trial_holds_its_reservation():
    ledger = Ledger(2.0)
    a = ledger.reserve([1.25])
    assert a is not None and ledger.free() == 0.75
    assert ledger.reserve([1.0]) is None  # $1.25 is held by the trial in flight
    cap = ledger.claim(a[0])
    assert cap == 2.0 and ledger.free() == 0.0
    assert ledger.reserve([0.01]) is None
    ledger.settle(a[0], 0.9)
    assert ledger.spent == 0.9 and round(ledger.free(), 9) == 1.1


# ---------- the in-trial cap reaches the agent ----------


def test_claude_code_gets_max_budget_usd_and_other_agents_do_not():
    req = TrialRequest(
        Path("/t"), Path("/tr"), "claude-code", "anthropic/" + SONNET, max_cost_usd=1.6875
    )
    assert _agent_kwargs(req) == {"max_budget_usd": "1.6875"}
    assert (
        _agent_kwargs(TrialRequest(Path("/t"), Path("/tr"), "codex", "gpt", max_cost_usd=1.0)) == {}
    )
    assert _agent_kwargs(TrialRequest(Path("/t"), Path("/tr"), "claude-code", "m")) == {}


def test_harbor_turns_the_cap_into_the_claude_flag():
    """The real Harbor agent, as harbor_executor configures it: no sandbox, no model call."""
    from harbor.agents.factory import AgentFactory
    from harbor.models.trial.config import AgentConfig

    req = TrialRequest(
        Path("/t"), Path("/tr"), "claude-code", "anthropic/" + SONNET, max_cost_usd=1.5
    )
    cfg = AgentConfig(name="claude-code", model_name=req.model, kwargs=_agent_kwargs(req))
    agent = AgentFactory.create_agent_from_config(cfg, logs_dir=Path(tempfile.mkdtemp()))
    assert "--max-budget-usd 1.5000" in agent.build_cli_flags()


def test_runner_passes_the_cap_and_marks_a_capped_trial_errored(tmp_path: Path):
    (tmp_path / "trials" / "fix__abc" / "agent").mkdir(parents=True)
    (tmp_path / "trials" / "fix__abc" / "agent" / "claude-code.txt").write_text(
        json.dumps({"type": "result", "subtype": "error_max_budget_usd", "total_cost_usd": 1.52})
    )
    rec = Recorder(result(0.0, cost=None))
    r = runner(tmp_path, rec)
    assert r.caps_cost and not r.free
    out = r.run_trial(replace(spec("with"), max_cost_usd=1.5))
    assert rec.requests[0].max_cost_usd == 1.5
    assert out.outcome == "errored"  # cut short at its cap: not a fail
    assert out.cost_usd == 1.52  # read from Claude Code's own stream when Harbor had none


def test_a_rate_limited_attempt_counts_and_comes_off_the_cap(tmp_path: Path):
    limited = result(exc="ApiRateLimitError", msg="429", cost=0.4)
    rec = Recorder(limited, result(1.0, cost=0.3))
    out = runner(tmp_path, rec).run_trial(replace(spec("with"), max_cost_usd=1.0))
    assert [q.max_cost_usd for q in rec.requests] == [1.0, 0.6]
    assert out.outcome == "pass" and abs(out.cost_usd - 0.7) < 1e-9


# ---------- after a run: a spend over the budget says why ----------


def test_overspend_before_the_cap_existed_says_so():
    from proving_ground.budget import overspend

    # The real run above: $2.90 of $2.00, made before the cap, no budget_cap in its meta.
    got = overspend(2.90, 2.00, {"agent": "claude-code"}, "2026-10-25T09:12:00+00:00")
    assert got == {
        "by_usd": 0.9,
        "before_cap": True,
        "note": "went over before the budget cap existed",
    }


def test_overspend_under_the_cap_names_the_last_trial():
    from proving_ground.budget import cap_record, overspend

    got = overspend(5.31, 5.0, {"budget_cap": cap_record()}, "2026-10-26T10:00:00+00:00")
    assert got["before_cap"] is False
    assert got["note"] == "over by $0.31 (the last trial cost more than predicted)"
    # A run made after the cap but without the record (a run from before it was recorded).
    got = overspend(2.5, 2.0, {}, "2026-10-26T10:00:00+00:00")
    assert got["note"] == "over by $0.50 (the last trial cost more than predicted)"


def test_no_overspend_note_within_the_budget_or_without_one():
    from proving_ground.budget import overspend

    assert overspend(1.99, 2.0, {}, "2026-01-01T00:00:00+00:00") is None
    assert overspend(2.004, 2.0, {}, "2026-01-01T00:00:00+00:00") is None  # rounding, not over
    assert overspend(3.0, None, {}, "2026-01-01T00:00:00+00:00") is None


def test_a_new_run_records_the_cap_it_runs_under(tmp_path):
    from proving_ground.budget import cap_record
    from proving_ground.service import prepare_experiment

    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("x")
    from proving_ground.files import save_scenario

    save_scenario(root, sc("a"))
    sk = tmp_path / "sk"
    sk.mkdir()
    (sk / "SKILL.md").write_text("---\nname: sk\n---\nx\n")
    p = prepare_experiment(root, sk, 2.0, n=1)
    meta = json.loads((root / ".proving-ground" / "runs" / str(p.eid) / "meta.json").read_text())
    assert meta["budget_cap"] == cap_record() == {"predict": B["predict"], "margin": B["margin"]}


# ---------- before a run: what it can detect ----------


def test_the_forecast_says_what_the_pairs_can_detect():
    from proving_ground.budget import forecast
    from proving_ground.stats import noise_half_width

    costs = CostModel(prior_usd(SONNET))
    f = forecast(costs, 6, budget=5.0)
    # $5 pays for 3 of the 6 pairs: the detectable effect is for the 3 it will reach, in whole
    # pts rounded up (80.02 -> 81: never a smaller change than the pairs can tell).
    assert f["pairs_in_budget"] == 3
    assert 0.80 < noise_half_width(3, B["detect_base_rate"]) < 0.81
    assert f["detect"] == {"pairs": 3, "pts": 81, "base_rate": 0.5}
    # More pairs, a narrower band: 40 pairs at 50% can't tell apart about ±22 pts.
    assert forecast(costs, 40)["detect"]["pts"] == 22
    assert forecast(costs, 6, budget=0.1)["detect"] is None  # not one pair fits


# ---------- the inverse of the sizing: what n pairs can tell apart ----------


def test_detectable_pts_is_the_inverse_of_the_sizing():
    from proving_ground.budget import detectable_pts, pairs_to_detect
    from proving_ground.stats import noise_half_width, pairs_for_half_width

    base = B["detect_base_rate"]
    assert detectable_pts(0) is None and detectable_pts(-1) is None
    assert pairs_to_detect(B["detect_target_pts"]) == 31  # the "about 31 pairs" of the sizing
    assert detectable_pts(31) == 25 and detectable_pts(30) == 26  # 30 pairs: ±25.3, not 25
    assert detectable_pts(20) == 31 and detectable_pts(1) == 139
    for n in range(1, 2001):
        d = detectable_pts(n)
        # The smallest whole pt at or above the half-width: never claims a smaller change.
        assert d - 1 < 100 * noise_half_width(n, base) <= d + 1e-9
        # Round trip: n pairs tell a ±d change, so sizing for d needs no more than n.
        assert pairs_to_detect(d) <= n
        assert pairs_to_detect(d) == pairs_for_half_width(d / 100, base)
    for t in range(1, 101):
        need = pairs_to_detect(t)
        assert detectable_pts(need) <= t  # the sized pairs tell the target apart
        assert need == 1 or detectable_pts(need - 1) > t  # one fewer doesn't
        for n in (need - 1, need, need + 1):
            if n > 0:  # exactly: n tells ±t apart when n reaches the sizing for t
                assert (detectable_pts(n) <= t) == (n >= need)


def test_the_full_label_says_what_the_budget_buys():
    from proving_ground.budget import forecast, full_size

    L = B["full_label"]
    # Enough for the sized pairs: the only state that says "conclusive".
    assert full_size(31, 31) == {
        "state": "conclusive",
        "pairs": 31,
        "planned_pairs": 31,
        "pts": 25,
        "text": L["conclusive"].format(pairs="31 pairs", pts=25),
    }
    assert full_size(31, 31)["text"] == "Full · 31 pairs · conclusive to ±25 pts"
    # The default full run (20 pairs) never reaches ±25, however big the budget.
    got = full_size(20, 20, pilot_pairs=4)
    assert got["state"] == "detects" and got["text"] == "Full · 20 pairs · tells apart ±31 pts"
    assert "conclusive" not in got["text"]
    # Stopped within the pilot's pairs: says so, like no_better_than_pilot.
    assert full_size(4, 20, pilot_pairs=4)["text"] == "Full · the budget only covers 4 pairs, as many as the pilot"
    assert full_size(1, 20, pilot_pairs=4)["text"] == "Full · the budget only covers 1 pair, as many as the pilot"
    assert full_size(5, 20, pilot_pairs=4)["state"] == "detects"
    assert full_size(0, 20, pilot_pairs=4)["text"] == L["nothing"]
    # From the forecast, whatever size is chosen: a $5 pilot request still says what Full buys.
    m = CostModel({"with": 0.95, "without": 0.04}, margin=1.0)
    pilot = forecast(m, 4, budget=5.0, pilot_pairs=4, full=21)
    assert pilot["full"]["text"] == "Full · 5 pairs · tells apart ±62 pts"  # 5 beat a 4-pair pilot
    assert pilot["full"] == full_size(5, 21, 4) and pilot["no_better_than_pilot"] is None
    assert forecast(m, 21, 50.0, 4, 21)["full"]["text"] == "Full · 21 pairs · tells apart ±31 pts"
    assert forecast(m, 31, 50.0, 4, 31)["full"]["state"] == "conclusive"
    assert forecast(m, 21, 3.0, 4, 21)["full"]["text"] == "Full · the budget only covers 3 pairs, as many as the pilot"
    assert "full" not in forecast(m, 21, 50.0)
    # A local model: the budget buys every pair.
    free = forecast(CostModel(prior_usd(SONNET), free=True), 4, 1.0, 4, 31)
    assert free["full"]["state"] == "conclusive"


def test_a_full_run_grows_with_the_budget_up_to_the_sizing():
    from proving_ground.budget import budget_for, forecast, full_pairs, pairs_to_detect, per_pair

    need = pairs_to_detect(B["detect_target_pts"])  # 31
    # At least the fixed full size; more as the budget pays for them, never past the sizing,
    # always in whole repeats of the tasks.
    assert full_pairs(5, 1.22, 5.0, 20) == 20
    assert full_pairs(5, 1.0, 25.0, 20) == 25
    assert full_pairs(5, 1.0, 27.0, 20) == 30  # 27 pairs: 6 whole repeats
    assert full_pairs(5, 1.22, 38.0, 20) == 35  # $38 reaches the 31: 7 repeats
    assert full_pairs(5, 1.0, 500.0, 20) == 35  # never past the sizing
    assert full_pairs(1, 1.0, 500.0, 20) == need
    assert full_pairs(40, 1.0, 500.0, 40) == 40  # more tasks than the sizing: one each
    assert full_pairs(5, 0.0, None, 20) == 35  # free: grows to the sizing
    assert full_pairs(0, 1.0, 5.0, 20) == 0
    # Taking the sizing's offer: the budget it names makes the full run conclusive.
    m = CostModel({"with": 0.95, "without": 0.04}, margin=1.0)
    pair = per_pair(m)
    assert abs(pair - 0.99) < 1e-9
    low = forecast(m, full_pairs(5, pair, 5.0, 20), 5.0, 5, full_pairs(5, pair, 5.0, 20), True)
    assert low["pairs"] == 20 and low["full"]["text"] == "Full · the budget only covers 5 pairs, as many as the pilot"
    # A budget alone reaches it now: the full run grows (the "Set budget" offer stands).
    assert low["sizing"]["enough_planned"] and not low["sizing"]["enough_budget"]
    usd = low["sizing"]["usd"]
    assert usd == budget_for(need, pair)
    planned = full_pairs(5, pair, usd, 20)
    got = forecast(m, planned, usd, 5, planned, True)
    assert got["pairs_in_budget"] == need and got["sizing"]["enough_budget"]
    assert got["full"]["text"] == "Full · 31 pairs · conclusive to ±25 pts"
    assert got["detect"]["pts"] == B["detect_target_pts"]


def test_cant_start_holds_one_with_trial_to_the_whole_budget():
    seen = CostModel(prior_usd(SONNET), {"with": [0.9, 1.0], "without": [0.05]})
    need = seen.estimate("with", [])[0]
    why = cant_start(seen, 1.0) if need > 1.0 else cant_start(seen, need - 0.01)
    assert why is not None and "can't pay for one trial" in why and "measured on 2 earlier trials" in why
    # The "without" may be reused, so a budget that pays for the "with" trial alone may start.
    assert cant_start(seen, need) is None
    # What it asks for, rounded up to the cent, is enough to start.
    asked = float(why.rsplit("$", 1)[1].rstrip("."))
    assert asked >= need and cant_start(seen, asked) is None
    assert cant_start(CostModel(prior_usd(SONNET), free=True), 0.0001) is None
