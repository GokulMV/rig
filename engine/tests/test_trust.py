"""Trust: results that aren't evidence, checks that aren't commands, and no model call unasked."""

import copy
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from proving_ground import adherence, validity
from proving_ground.api.app import create_app
from proving_ground.files import load_scenarios, save_scenario
from proving_ground.generate.client import ToolCall
from proving_ground.models import Scenario
from proving_ground.service import ServiceError, prepare_experiment

BASE = "http://127.0.0.1:7357"
ORIGIN = {"origin": BASE}


@dataclass
class T:
    arm: str
    scenario_id: str
    outcome: str


def _pairs(rates: dict[str, tuple[str, str]], n: int = 2) -> list[T]:
    return [
        T(arm, sid, out)
        for sid, (w, wo) in rates.items()
        for _ in range(n)
        for arm, out in (("with", w), ("without", wo))
    ]


# ---------- Is a result evidence? ----------


def test_a_workflow_never_opened_makes_the_result_invalid():
    trials = _pairs({"a": ("pass", "fail"), "b": ("fail", "pass")})
    # Followed 0 of 3, never opened in 3.
    never = {"read": 3, "followed": 0, "not_opened": 3, "not_applied": 3}
    v = validity.judge(trials, never)
    assert v["status"] == "invalid" and v["badge"] == "Invalid: the workflow was never opened"
    some = validity.judge(trials, never | {"not_applied": 2})
    assert some["badge"] == "Invalid: the workflow wasn't opened in 2 of 3 trials"
    # Half or fewer skipped (max_not_applied_share 0.5), or no logs to read: still valid.
    assert validity.judge(trials, never | {"read": 4, "not_applied": 2})["status"] == "valid"
    assert validity.judge(trials, {"read": 0, "not_applied": 0})["status"] == "valid"
    assert validity.judge(trials, None)["status"] == "valid"


def test_an_mcp_server_never_called_makes_the_result_invalid():
    trials = _pairs({"a": ("pass", "fail")})
    v = validity.judge(trials, mcp_usage={"read": 4, "used": 0})
    assert v["badge"] == "Invalid: the MCP server was never used"
    assert validity.judge(trials, mcp_usage={"read": 4, "used": 3})["status"] == "valid"


def test_no_task_won_or_lost_is_uninformative():
    p = validity.judge(_pairs({"a": ("pass", "pass"), "b": ("pass", "pass")}))
    assert (p["status"], p["badge"]) == ("uninformative", "Uninformative: both always pass")
    f = validity.judge(_pairs({"a": ("fail", "fail")}))
    assert f["badge"] == "Uninformative: both always fail"
    mixed = validity.judge(_pairs({"a": ("pass", "pass"), "b": ("fail", "fail")}))
    assert mixed["badge"] == "Uninformative: each task passes both ways or fails both ways"
    # One task that went differently is enough to be evidence; so is a task that sometimes passes.
    assert (
        validity.judge(_pairs({"a": ("pass", "pass"), "b": ("pass", "fail")}))["status"] == "valid"
    )
    flaky = [T("with", "a", "pass"), T("with", "a", "fail"), T("without", "a", "pass")]
    assert validity.judge(flaky + [T("without", "a", "pass")])["status"] == "valid"
    # Errored trials count for nothing; with nothing finished there is nothing to judge.
    assert validity.judge([T("with", "a", "error")])["status"] == "valid"


def test_a_broken_check_comes_first():
    v = validity.judge(
        _pairs({"a": ("fail", "fail")}), {"read": 2, "not_applied": 2}, broken={"a": "x"}
    )
    assert v["badge"] == "Invalid: the check is broken" and "a" in v["reason"]


def test_adherence_counts_trials_that_never_got_the_workflow():
    never = adherence.Adherence(True, 3, opened=False)  # not opened, no step run
    good = adherence.Adherence(True, 3, steps_run=3, models_ok=3, opened=True)
    codex = adherence.Adherence(True, 3, opened=None)  # no Skill call to see, and no step ran
    partial = adherence.Adherence(True, 3, steps_run=2, opened=None)
    # Ran every step with no Skill call in its log: it got the workflow.
    unseen = adherence.Adherence(True, 3, steps_run=3, models_ok=3, opened=False)
    glanced = adherence.Adherence(True, 3, opened=True)  # opened it, then did it its own way
    s = adherence.summarize([never, good, codex, partial, unseen, glanced])
    assert s["not_opened"] == 2 and s["not_applied"] == 2 and s["read"] == 6


# ---------- Is a check a command? ----------


@pytest.mark.parametrize(
    "check",
    [
        "pytest -q tests/test_refunds.py",
        "python3 /tests/checks/a/check.py",
        "bash tests/test.sh",
        "npm test",
        "npm run test",
        "make test",
        "make quality",
        "go test ./...",
        "true",
        "./scripts/check.sh",
        "CI=1 FOO=bar pytest -x",
        "# the refund rules\n\ngrep -q escalate refunds.py",
        "test -f out.txt && grep -q done out.txt",
        "python3 -c \"import refunds\nassert refunds.refund('basic', 200) == 'escalate'\"",
        "set -e\npytest",
        "[ -f out.txt ]",
    ],
)
def test_commands_are_accepted(check):
    assert validity.check_problem(check) is None


@pytest.mark.parametrize(
    ("check", "says"),
    [
        ("token cost", "`token` is not a program"),
        ("Token cost under $0.10", "is not a program"),
        ("make sure the tests pass", "reads as a sentence"),
        ("check that refunds work correctly", "is not a program"),
        ("The agent escalates the refund", "is not a program"),
        ("FOO=1", "only sets variables"),
        ("don't break the build", "a quote is never closed"),
        ("# just a note", "only comments"),
        ("   ", "no check"),
    ],
)
def test_prose_is_rejected(check, says):
    why = validity.check_problem(check)
    assert why is not None and says in why


def test_approve_create_and_run_refuse_a_check_that_isnt_a_command(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    root = tmp_path / "shop"
    root.mkdir()
    (root / "app.py").write_text("x")
    save_scenario(root, Scenario(id="cost", instruction="Keep it cheap.", check="token cost"))
    save_scenario(root, Scenario(id="ok", instruction="Fix.", check="pytest -q"))
    # Approved before checks were validated: shown with a warning, never run.
    save_scenario(
        root,
        Scenario(id="old", instruction="Fix.", check="token cost", check_status="approved"),
    )
    c = TestClient(create_app(root, user_skills_dir=root / "none"), base_url=BASE)
    r = c.post("/api/scenarios/cost/approve", headers=ORIGIN)
    assert r.status_code == 422
    assert (
        "can't be approved" in r.json()["detail"]
        and "`token` is not a program" in r.json()["detail"]
    )
    assert c.post("/api/scenarios/ok/approve", headers=ORIGIN).status_code == 200
    new = {"id": "mine", "instruction": "Do it.", "check": "make sure it works"}
    r = c.post("/api/scenarios", json=new, headers=ORIGIN)
    assert r.status_code == 422 and "reads as a sentence" in r.json()["detail"]
    listed = {s["id"]: s for s in c.get("/api/scenarios").json()}
    assert listed["old"]["runnable"] and "not a program" in listed["old"]["check_problem"]
    assert listed["ok"]["check_problem"] is None
    # A run on it is refused, naming it, before anything is spent.
    sk = tmp_path / "skills" / "tdd"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("---\nname: tdd\n---\nTest first.\n")
    with pytest.raises(ServiceError, match="old: `token cost` isn't a command"):
        prepare_experiment(root, sk, 1.0, scenario_ids=["old", "ok"])
    r = c.post(
        "/api/experiments",
        json={"treatment_path": str(sk), "budget": 1, "n": 2, "scenario_ids": ["old"]},
        headers=ORIGIN,
    )
    assert r.status_code == 422 and "old:" in r.json()["detail"]
    assert not (root / ".proving-ground" / "runs").exists()


# ---------- Written for a different goal ----------


def test_scenarios_remember_the_use_case_they_were_written_for(tmp_path, monkeypatch, plan_data):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    class Fake:
        def call(self, prompt, tool, model, max_tokens):
            return ToolCall(copy.deepcopy(plan_data), "tool_use", 1, 1)

    monkeypatch.setattr("proving_ground.generate.client.make_client", Fake)
    root = tmp_path / "shop"
    root.mkdir()
    (root / "app.py").write_text("x")
    # Generated before scenarios remembered their goal: no stamp yet.
    save_scenario(root, Scenario(id="legacy", instruction="x", check="true", origin="generated"))
    save_scenario(root, Scenario(id="own", instruction="x", check="true", origin="user"))
    c = TestClient(create_app(root, user_skills_dir=root / "none"), base_url=BASE)
    c.put("/api/usecase", json={"text": "Handle refunds."}, headers=ORIGIN)
    body = c.post("/api/generate", json={"mix": "typical=1,failure=1,imaginary=1"}, headers=ORIGIN)
    assert body.status_code == 200, body.text
    assert all(s["goal_changed"] is False for s in body.json()["scenarios"])
    stamps = {s.id: s.written_for for s in load_scenarios(root)}
    assert stamps["refund-basic"] == validity.use_case_tag("Handle refunds.")

    def changed():
        return {s["id"]: s["goal_changed"] for s in c.get("/api/scenarios").json()}

    # Saving the same words again (spacing, case) changes nothing.
    c.put("/api/usecase", json={"text": "  handle   refunds. "}, headers=ORIGIN)
    assert changed()["refund-basic"] is False
    c.put("/api/usecase", json={"text": "Answer billing questions."}, headers=ORIGIN)
    now = changed()
    assert now["refund-basic"] is True and now["legacy"] is True
    assert now["own"] is False  # you wrote it yourself: it isn't flagged
    # Back to the goal they were written for: no longer flagged.
    c.put("/api/usecase", json={"text": "Handle refunds."}, headers=ORIGIN)
    assert changed()["refund-basic"] is False


# ---------- No model call unless asked ----------


class CountingCli:
    calls: list = []

    def call(self, prompt, tool, model, max_tokens):
        CountingCli.calls.append(tool["name"])
        if tool["name"] == "emit_estimate":
            data = {"low": -5, "high": 9, "likely": 3, "confidence": "low", "reason": "x"}
        else:
            data = {"picks": [], "create": [], "improve": []}
        return ToolCall(data, "tool_use", 1, 1)


def test_estimates_and_picks_ask_a_model_only_when_the_request_says_so(tmp_path: Path):
    from test_api_workspace import FakeGitHub

    from proving_ground.agents import Credentials
    from proving_ground.workspace import Workspace

    CountingCli.calls = []
    a = tmp_path / "shop"
    sk = a / ".claude" / "skills" / "tdd"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("---\nname: tdd\ndescription: Test first.\n---\nTest first.\n")
    app = create_app(
        workspace=Workspace(tmp_path / "home" / "ws.json"),
        credentials=Credentials(env={}, home=tmp_path / "userhome"),
        github=FakeGitHub(),
        home=tmp_path / "home",
        user_skills_dir=tmp_path / "none",
        web_dist=tmp_path / "nodist",
        host_login=lambda: {"email": "me@example.com", "plan": "max", "method": "claude.ai"},
        cli_model=CountingCli,
    )
    c = TestClient(app, base_url=BASE)
    c.post("/api/repos", json={"path": str(a)}, headers=ORIGIN)
    for body in ({}, {"quick": True}, {"quick": True, "model": True}):
        e = c.post(
            "/api/estimate", json={"treatment_path": str(sk), "steps": []} | body, headers=ORIGIN
        ).json()
        assert e["basis"] == "rough" and e["sharpen_usd"] == 0.01
    assert CountingCli.calls == []
    e = c.post(
        "/api/estimate", json={"treatment_path": str(sk), "model": True}, headers=ORIGIN
    ).json()
    assert e["basis"] == "estimate" and CountingCli.calls == ["emit_estimate"]

    CountingCli.calls = []
    rough = c.get("/api/recommend", params={"category": "skill"}).json()
    again = c.get("/api/recommend", params={"category": "skill", "refresh": True}).json()
    assert rough["basis"] == again["basis"] == "rough" and rough["model_pick_usd"] == 0.02
    assert CountingCli.calls == []
    picked = c.get("/api/recommend", params={"category": "skill", "model": True}).json()
    assert len(CountingCli.calls) == 1 and picked["basis"] == "model"
    # The model's picks are kept: shown again without a call until the repo's needs change.
    assert c.get("/api/recommend", params={"category": "skill"}).json()["basis"] == "model"
    assert len(CountingCli.calls) == 1


def test_a_repo_run_that_isnt_evidence_is_badged_and_not_used_as_a_measurement(
    tmp_path: Path, monkeypatch
):
    """Both arms always pass: the experiment says so, and the skill's estimate stays rough."""
    import time
    from types import SimpleNamespace

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(
        "proving_ground.runner.harbor.harbor_executor",
        lambda req: SimpleNamespace(
            exception_info=None,
            verifier_result=SimpleNamespace(rewards={"reward": 0.0 if req.agent == "nop" else 1.0}),
            agent_result=SimpleNamespace(n_input_tokens=1, n_output_tokens=1, cost_usd=0.01),
            started_at=None,
            finished_at=None,
            trial_name="t",
        ),
    )
    root = tmp_path / "proj"
    root.mkdir()
    (root / "app.py").write_text("x")
    save_scenario(root, Scenario(id="a", instruction="Fix.", check="true", check_status="approved"))
    sk = tmp_path / "skills" / "tdd"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("---\nname: tdd\n---\nTest first.\n")
    c = TestClient(create_app(root, user_skills_dir=root / "none"), base_url=BASE)
    r = c.post(
        "/api/experiments", json={"treatment_path": str(sk), "n": 2, "budget": 5}, headers=ORIGIN
    )
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    for _ in range(400):
        d = c.get(f"/api/experiments/{eid}").json()
        if d["status"] != "running" and d["trials"]:
            break
        time.sleep(0.05)
    assert d["validity"]["badge"] == "Uninformative: both always pass"
    est = c.post("/api/estimate", json={"treatment_path": str(sk)}, headers=ORIGIN).json()
    assert est["basis"] == "rough" and "isn't evidence" in est["note"]
