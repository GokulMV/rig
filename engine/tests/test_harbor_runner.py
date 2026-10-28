from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from proving_ground.models import Scenario, Treatment, TreatmentKind
from proving_ground.runner.base import TrialSpec
from proving_ground.runner.harbor import AgentAuthError, HarborRunner, TrialRequest, classify

T0 = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
SKILL = Treatment(kind=TreatmentKind.SKILL, name="tdd", path="/skills/tdd", content_hash="d" * 64)
SC = Scenario(id="fix", instruction="x", check="true", check_status="approved")


def result(reward=None, exc=None, msg="", name="fix__abc", cost=0.12, tin=1000, tout=200):
    return SimpleNamespace(
        exception_info=SimpleNamespace(exception_type=exc, exception_message=msg) if exc else None,
        verifier_result=SimpleNamespace(rewards={"reward": reward}) if reward is not None else None,
        agent_result=SimpleNamespace(n_input_tokens=tin, n_output_tokens=tout, cost_usd=cost),
        started_at=T0,
        finished_at=T0 + timedelta(seconds=42),
        trial_name=name,
    )


class Recorder:
    def __init__(self, *results):
        self.results = list(results)
        self.requests: list[TrialRequest] = []

    def __call__(self, req: TrialRequest):
        self.requests.append(req)
        return self.results.pop(0)


def runner(tmp_path: Path, executor, sleeps=None) -> HarborRunner:
    return HarborRunner(
        {"fix": tmp_path / "tasks" / "fix"},
        tmp_path / "trials",
        "anthropic/claude-sonnet-5-5",
        executor=executor,
        backoff_s=1.0,
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
    )


def spec(arm, repeat=0):
    return TrialSpec(1, SC, arm, repeat, SKILL, "claude-sonnet-5-5", 0, Path("/repo"))


def test_classify():
    assert classify(result(1.0)) == ("pass", "")
    assert classify(result(0.0)) == ("fail", "")
    assert classify(result(None))[0] == "errored"
    # An agent timeout is a fail (it didn't finish in the task's limit), even when the check
    # passed afterwards; the limit comes from Harbor's message, else the trial's duration.
    assert classify(
        result(1.0, exc="AgentTimeoutError", msg="Agent execution timed out after 600.0 seconds")
    ) == ("fail", "timed out after 600 s")
    assert classify(result(1.0, exc="AgentTimeoutError", msg="timed out")) == (
        "fail",
        "timed out after 42 s",
    )
    # Other exceptions stay errored.
    assert classify(result(1.0, exc="RuntimeError", msg="boom")) == (
        "errored",
        "RuntimeError: boom",
    )
    assert (
        classify(result(exc="RuntimeError", msg="Docker compose command failed for env"))[0]
        == "broken"
    )
    with pytest.raises(AgentAuthError):
        classify(result(exc="AgentAuthenticationError", msg="Not logged in"))


def test_arms_differ_only_by_skill(tmp_path: Path):
    rec = Recorder(result(1.0), result(0.0))
    r = runner(tmp_path, rec)
    with_ = r.run_trial(spec("with"))
    without = r.run_trial(spec("without"))
    a, b = rec.requests
    assert (a.agent, a.model, a.skills) == (
        "claude-code",
        "anthropic/claude-sonnet-5-5",
        ("/skills/tdd",),
    )
    assert (b.agent, b.model, b.skills) == ("claude-code", "anthropic/claude-sonnet-5-5", ())
    assert a.task_dir == b.task_dir == tmp_path / "tasks" / "fix"
    assert (with_.outcome, without.outcome) == ("pass", "fail")
    assert (with_.tokens_in, with_.tokens_out, with_.cost_usd, with_.duration_s) == (
        1000,
        200,
        0.12,
        42.0,
    )
    assert with_.transcript_uri == str(tmp_path / "trials" / "fix__abc")


def test_exit_code_is_read_from_verifier_dir(tmp_path: Path):
    d = tmp_path / "trials" / "fix__abc" / "verifier"
    d.mkdir(parents=True)
    (d / "exit_code.txt").write_text("3\n")
    assert runner(tmp_path, Recorder(result(0.0))).run_trial(spec("with")).exit_code == 3


def test_rate_limits_are_retried_with_backoff(tmp_path: Path):
    sleeps: list[float] = []
    rec = Recorder(
        result(exc="ApiRateLimitError", msg="429"),
        result(exc="ApiRateLimitError", msg="429"),
        result(1.0),
    )
    out = runner(tmp_path, rec, sleeps).run_trial(spec("with"))
    assert out.outcome == "pass"
    assert sleeps == [1.0, 2.0]


def test_rate_limit_gives_up_after_three_attempts(tmp_path: Path):
    rec = Recorder(*[result(exc="ApiRateLimitError", msg="429") for _ in range(3)])
    assert runner(tmp_path, rec).run_trial(spec("with")).outcome == "errored"
    assert len(rec.requests) == 3


def test_non_skill_treatments_rejected(tmp_path: Path):
    loop = Treatment(kind=TreatmentKind.LOOP, name="retry", path="/x", content_hash="e" * 64)
    with pytest.raises(ValueError, match="loop treatments are not supported yet"):
        runner(tmp_path, Recorder()).run_trial(
            TrialSpec(1, SC, "with", 0, loop, "m", 0, Path("/r"))
        )


def test_preflight_uses_nop_agent(tmp_path: Path):
    rec = Recorder(
        result(0.0), result(1.0), result(exc="RuntimeError", msg="Docker compose command failed")
    )
    r = runner(tmp_path, rec)
    p1, p2, p3 = (r.preflight(SC, Path("/repo")) for _ in range(3))
    assert (p1.setup_ok, p1.check_passed_without_agent) == (True, False)
    assert (p2.setup_ok, p2.check_passed_without_agent) == (True, True)
    assert (p3.setup_ok, p3.check_passed_without_agent) == (False, False)
    assert "Docker compose command failed" in p3.log
    assert {req.agent for req in rec.requests} == {"nop"}
    assert rec.requests[0].trials_dir == tmp_path / "trials" / "preflight"


def test_agent_and_credentials_reach_harbor(tmp_path):
    seen = []

    def executor(req):
        seen.append(req)
        return SimpleNamespace(
            exception_info=None,
            verifier_result=SimpleNamespace(rewards={"reward": 1.0}),
            agent_result=None,
            started_at=None,
            finished_at=None,
            trial_name="t",
        )

    r = HarborRunner(
        {"fix": tmp_path},
        tmp_path,
        None,
        executor=executor,
        agent="codex",
        env={"OPENAI_API_KEY": "k"},
    )
    r.run_trial(spec("with"))
    assert seen[0].agent == "codex" and dict(seen[0].env) == {"OPENAI_API_KEY": "k"}


def test_an_agent_timeout_is_recorded_as_a_timed_out_fail(tmp_path: Path):
    msg = "Agent execution timed out after 600.0 seconds"
    r = runner(tmp_path, Recorder(result(1.0, exc="AgentTimeoutError", msg=msg), result(0.0)))
    t = r.run_trial(spec("with"))
    assert (t.outcome, t.detail, t.timed_out) == ("fail", "timed out after 600 s", True)
    plain = r.run_trial(spec("without"))
    assert (plain.outcome, plain.detail, plain.timed_out) == ("fail", None, False)


def test_old_errored_timeouts_become_timed_out_fails_in_a_one_time_migration(tmp_path: Path):
    """A trial stored as errored before this rule: when the store opens, its Harbor
    result.json says what it was. The migration runs once per database; reads never write."""
    import json
    import sqlite3

    from proving_ground.models import ScenarioKind
    from proving_ground.store import Store
    from proving_ground.trial import TrialOutcome

    def trial_dir(name: str, exc: dict | None) -> str:
        d = tmp_path / name
        d.mkdir()
        (d / "result.json").write_text(json.dumps({"exception_info": exc}))
        return str(d)

    db = tmp_path / "pg.db"
    st = Store(f"sqlite:///{db}")
    pid = st.ensure_project(str(tmp_path))
    eid = st.create_experiment(pid, SKILL, "m", 1, 1.0, 0)
    timeout = {
        "exception_type": "AgentTimeoutError",
        "exception_message": "timed out after 600.0 seconds",
    }
    other = {"exception_type": "RuntimeError", "exception_message": "boom"}
    for i, (sid, uri) in enumerate(
        [("a", trial_dir("a", timeout)), ("b", trial_dir("b", other)), ("c", None)]
    ):
        st.record_trial(
            eid, TrialOutcome(sid, ScenarioKind.TYPICAL, "with", i, "errored", transcript_uri=uri)
        )
    # Reading doesn't rewrite anything: these were recorded after this database's migration.
    assert all(t.outcome == "errored" for t in st.trials(eid))
    # A database from before the rule: no record of the migration.
    with sqlite3.connect(db) as c:
        c.execute("DELETE FROM migrations")
    got = {t.scenario_id: t for t in Store(f"sqlite:///{db}").trials(eid)}
    assert (got["a"].outcome, got["a"].detail, got["a"].timed_out) == (
        "fail",
        "timed out after 600 s",
        True,
    )
    assert (got["b"].outcome, got["b"].detail) == ("errored", "RuntimeError: boom")
    assert (got["c"].outcome, got["c"].detail) == ("errored", None)
    # Recorded: opening again runs nothing, so a later errored timeout without detail stays.
    st2 = Store(f"sqlite:///{db}")
    st2.record_trial(
        eid,
        TrialOutcome(
            "d", ScenarioKind.TYPICAL, "with", 9, "errored", transcript_uri=trial_dir("d", timeout)
        ),
    )
    again = {t.scenario_id: (t.outcome, t.detail) for t in Store(f"sqlite:///{db}").trials(eid)}
    assert again["a"] == ("fail", "timed out after 600 s") and again["d"] == ("errored", None)
