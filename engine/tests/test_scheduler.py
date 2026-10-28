from pathlib import Path

import pytest

from proving_ground.models import Scenario, Treatment, TreatmentKind
from proving_ground.runner.base import PreflightResult, TrialSpec
from proving_ground.runner.fake import FakeRunner
from proving_ground.scheduler import (
    NotRunnableError,
    PreflightError,
    plan_trials,
    repeats_for,
    run_experiment,
)
from proving_ground.stats import Verdict
from proving_ground.store import Store

TREAT = Treatment(kind=TreatmentKind.SKILL, name="tdd", path="/x", content_hash="b" * 64)


def sc(sid, **kw):
    return Scenario(id=sid, instruction="do it", check="exit 0", check_status="approved", **kw)


@pytest.fixture
def env():
    store = Store("sqlite://")
    pid = store.ensure_project("/repo")
    eid = store.create_experiment(pid, TREAT, "m", repeats=2, budget_usd=100.0, seed=1)
    return store, eid


def go(store, eid, runner, scenarios, repeats=2, budget=100.0, events=None):
    return run_experiment(
        store,
        runner,
        eid,
        scenarios,
        TREAT,
        Path("/repo"),
        "m",
        1,
        repeats,
        budget,
        on_event=(events.append if events is not None else None),
    )


def test_repeats_for():
    assert repeats_for(40, 3) == 14
    assert repeats_for(10, 10) == 1
    with pytest.raises(ValueError):
        repeats_for(10, 0)


def test_plan_alternates_arm_order():
    a, b = sc("a"), sc("b")
    plan = [(s.id, r, arm) for s, r, arm in plan_trials([a, b], 2)]
    assert plan == [
        ("a", 0, "with"),
        ("a", 0, "without"),
        ("b", 0, "with"),
        ("b", 0, "without"),
        ("a", 1, "without"),
        ("a", 1, "with"),
        ("b", 1, "without"),
        ("b", 1, "with"),
    ]


def test_refuses_unapproved_scenarios(env):
    store, eid = env
    with pytest.raises(NotRunnableError) as e:
        go(store, eid, FakeRunner(lambda s: "pass"), [sc("a"), Scenario(id="b", instruction="x")])
    assert e.value.ids == ["b"]


def test_preflight_pass_without_agent_stops_run(env):
    store, eid = env
    runner = FakeRunner(
        lambda s: "pass", preflight={"a": PreflightResult("a", True, True, "check exited 0")}
    )
    with pytest.raises(PreflightError) as e:
        go(store, eid, runner, [sc("a"), sc("b")])
    assert [r.scenario_id for r in e.value.results] == ["a"]
    assert runner.calls == []
    assert store.get_experiment(eid).status == "failed_preflight"


def test_setup_failure_marks_scenario_broken_and_skips_it(env):
    store, eid = env
    events = []
    runner = FakeRunner(
        lambda s: "pass", preflight={"a": PreflightResult("a", False, False, "seed failed")}
    )
    go(store, eid, runner, [sc("a"), sc("b")], events=events)
    assert {s.scenario.id for s in runner.calls} == {"b"}
    broken = [t for t in store.trials(eid) if t.outcome == "broken"]
    assert {(t.scenario_id, t.arm) for t in broken} == {("a", "with"), ("a", "without")}
    assert any(e["type"] == "broken" and e["scenario_id"] == "a" for e in events)


def test_full_run_detects_helpful_treatment(env):
    store, eid = env

    def decide(spec: TrialSpec) -> str:
        if spec.arm == "with":
            return "pass"
        return "pass" if spec.repeat % 4 == 0 else "fail"

    summary = go(store, eid, FakeRunner(decide), [sc("a"), sc("b")], repeats=20)
    assert summary.headline.n_pairs == 40
    assert summary.verdict is Verdict.HELPS
    assert store.get_experiment(eid).status == "done"


def test_budget_stop_then_resume(env):
    store, eid = env
    events = []
    runner = FakeRunner(lambda s: "pass", cost_per_trial=1.0)
    go(store, eid, runner, [sc("a")], repeats=4, budget=3.0, events=events)
    # One whole pair ($2): the next is predicted at $1.25 an arm, more than the $1 left.
    assert len(store.trials(eid)) == 2
    assert store.get_experiment(eid).status == "stopped_budget"
    assert events[-1]["type"] == "stopped_budget"
    runner2 = FakeRunner(lambda s: "pass", cost_per_trial=1.0)
    summary = go(store, eid, runner2, [sc("a")], repeats=4, budget=100.0)
    assert len(runner2.calls) == 6
    assert len(store.trials(eid)) == 8
    assert summary.headline.n_pairs == 4
    assert store.get_experiment(eid).status == "done"


def test_errored_trials_recorded_and_excluded(env):
    store, eid = env
    runner = FakeRunner(lambda s: "errored" if (s.arm == "with" and s.repeat == 0) else "pass")
    summary = go(store, eid, runner, [sc("a")], repeats=3)
    assert summary.errored == 1
    assert summary.headline.n_pairs == 2
    assert summary.unreliable is True
