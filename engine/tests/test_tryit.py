"""Try it: one run per pasted input, the answer read back, a hard budget, optional grading."""

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from proving_ground import tryit
from proving_ground.agents import Credentials
from proving_ground.api.app import create_app
from proving_ground.budget import CostModel
from proving_ground.files import load_scenarios
from proving_ground.models import treatment_from_path
from proving_ground.runner.harbor import HarborRunner
from proving_ground.workspace import Workspace

BASE = "http://127.0.0.1:7357"
ORIGIN = {"origin": BASE}

WF = {
    "id": "refunds",
    "name": "Answer refund emails",
    "discipline": "support",
    "origin": "custom",
    "steps": [
        {"id": "read", "name": "Read the email", "does": "Read it.", "kind": "think",
         "model": "claude-sonnet-5-5"},
        {"id": "policy", "name": "Check the policy", "does": "Refunds within 30 days.",
         "kind": "do", "model": "claude-sonnet-5-5"},
        {"id": "reply", "name": "Write the reply", "does": "Write it.", "kind": "do",
         "model": "claude-sonnet-5-5"},
    ],
}  # fmt: skip


def write_trial(trial: Path, answer: str | None, subtype="success", steps=(), cost=0.3):
    """What Claude Code leaves in a trial folder: its stream (closing result event) and session."""
    (trial / "agent" / "sessions").mkdir(parents=True, exist_ok=True)
    lines = ['{"type":"system"}']
    if answer is not None or subtype != "success":
        ev = {"type": "result", "subtype": subtype, "total_cost_usd": cost}
        if answer is not None:
            ev["result"] = answer
        lines.append(json.dumps(ev))
    (trial / "agent" / "claude-code.txt").write_text("\n".join(lines) + "\n")
    calls = [
        {"type": "tool_use", "name": "Agent", "input": {"description": s, "model": "sonnet"}}
        for s in steps
    ]
    (trial / "agent" / "sessions" / "s.jsonl").write_text(
        json.dumps({"message": {"content": calls}}) + "\n"
    )


class Executor:
    """Harbor, faked: answers with the input's first line, records every request."""

    def __init__(self, cost=0.3, subtype="success", steps=("Read the email", "Write the reply")):
        self.requests = []
        self.cost, self.subtype, self.steps = cost, subtype, steps
        self.instructions = []

    def __call__(self, req):
        self.requests.append(req)
        text = (req.task_dir / "instruction.md").read_text()
        self.instructions.append(text)
        name = f"{req.task_dir.name}__{len(self.requests)}"
        answer = None if self.subtype != "success" else f"Reply to: {text.splitlines()[0]}"
        write_trial(req.trials_dir / name, answer, self.subtype, self.steps, self.cost)
        return SimpleNamespace(
            exception_info=None,
            verifier_result=SimpleNamespace(rewards={"reward": 1.0}),
            agent_result=SimpleNamespace(n_input_tokens=10, n_output_tokens=5, cost_usd=self.cost),
            started_at=None,
            finished_at=None,
            trial_name=name,
        )


# ---------- reading the answer back ----------


def test_the_answer_is_claude_codes_closing_result(tmp_path: Path):
    write_trial(tmp_path / "t", "Hi Dana, yes: a full refund.")
    assert tryit.final_answer(tmp_path / "t", "claude-code") == "Hi Dana, yes: a full refund."


def test_other_agents_answer_from_the_trajectory(tmp_path: Path):
    t = tmp_path / "t" / "agent"
    t.mkdir(parents=True)
    steps = [
        {"source": "user", "message": "the email"},
        {"source": "agent", "message": [{"type": "text", "text": "Refund approved."}]},
        {"source": "agent", "message": ""},  # a tool-only step: not the answer
    ]
    (t / "trajectory.json").write_text(json.dumps({"steps": steps}))
    assert tryit.final_answer(tmp_path / "t", "codex") == "Refund approved."
    assert tryit.final_answer(tmp_path / "missing", "codex") is None


def test_a_long_answer_is_cut_and_says_so(tmp_path: Path):
    write_trial(tmp_path / "t", "x" * (tryit.T["max_answer_chars"] + 50))
    got = tryit.final_answer(tmp_path / "t", "claude-code")
    assert got.endswith("(cut here)") and len(got) < tryit.T["max_answer_chars"] + 20


# ---------- the run itself, with the real HarborRunner and a fake executor ----------


def setup(tmp_path: Path, ex: Executor, n: int, workflow=True):
    from proving_ground import lab

    if workflow:
        folder = lab.compile_workflow(lab.load_workflow(WF), tmp_path / "workflow-refunds")
    else:
        folder = tmp_path / "tone"
        folder.mkdir()
        (folder / "SKILL.md").write_text("---\nname: tone\n---\nBe kind.\n")
    t = treatment_from_path(folder)
    runner, root = tryit.prepare(tmp_path / "work", t, n, "claude-code", "anthropic/x", {})
    runner._executor = ex  # noqa: SLF001 - the test's Harbor
    tasks = {f"try-{i + 1}": tmp_path / "work" / "tasks" / f"try-{i + 1}" for i in range(n)}
    return runner, root, t, tasks


def job(inputs, budget=5.0, grade=False):
    return tryit.TryJob(inputs, budget, "claude-code", "claude-sonnet-5-5", "x", True, grade)


def test_each_input_runs_once_as_a_with_trial_and_its_answer_comes_back(tmp_path: Path):
    ex = Executor()
    runner, root, t, tasks = setup(tmp_path, ex, 2)
    j = job(["I want a refund, order 1", "Where is my parcel?"])
    tryit.run(j, runner, t, root, CostModel({"with": 1.0, "without": 0.25}), tasks, WF)
    assert j.status == "done"
    a, b = j.results
    assert (a.status, a.answer) == ("done", "Reply to: I want a refund, order 1")
    assert b.answer == "Reply to: Where is my parcel?"
    assert a.steps == {"kind": "workflow", "steps": 3, "ran": 2, "missing": ["Check the policy"]}
    assert a.cost_usd == 0.3 and j.spent_usd == pytest.approx(0.6)
    # As a "with" arm: the workflow handed over, its prompt naming it; the input is the task.
    r = ex.requests[0]
    assert r.skills == (t.path,) and r.prompt_template is not None
    assert ex.instructions[0].startswith("I want a refund, order 1\n\n" + tryit.T["answer_note"])
    # Nothing kept: the inputs were on disk only while their own trial ran.
    assert not tasks["try-1"].exists() and not list((tmp_path / "work" / "trials").glob("try-*"))


def test_the_budget_is_a_hard_cap_passed_to_claude_code(tmp_path: Path):
    ex = Executor(cost=0.3)
    runner, root, t, tasks = setup(tmp_path, ex, 2)
    j = job(["a", "b"], budget=3.0)
    tryit.run(j, runner, t, root, CostModel({"with": 1.0, "without": 0.25}), tasks, WF)
    # The first input may spend everything; the second what the first left.
    assert ex.requests[0].max_cost_usd == pytest.approx(3.0)
    assert ex.requests[1].max_cost_usd == pytest.approx(2.7)


def test_an_input_cut_short_at_its_cap_says_so(tmp_path: Path):
    ex = Executor(subtype="error_max_budget_usd")
    runner, root, t, tasks = setup(tmp_path, ex, 1)
    j = job(["a"], budget=2.0)
    tryit.run(j, runner, t, root, CostModel({"with": 1.0, "without": 0.25}), tasks, WF)
    assert j.results[0].status == "capped" and "cap" in j.results[0].detail


def test_inputs_the_budget_cant_pay_for_are_skipped(tmp_path: Path):
    ex = Executor(cost=1.2)
    runner, root, t, tasks = setup(tmp_path, ex, 3)
    j = job(["a", "b", "c"], budget=1.3)  # the first is predicted at $1.25 and fits
    tryit.run(j, runner, t, root, CostModel({"with": 1.0, "without": 0.25}), tasks, WF)
    # It cost $1.20, so the next is predicted at $1.50 with $0.10 left: not started.
    assert [r.status for r in j.results] == ["done", "skipped", "skipped"]
    assert j.status == "stopped_budget" and len(ex.requests) == 1
    assert "would cost about $1.50 and $0.10 is left" in j.results[1].detail
    ex2 = Executor()
    runner, root, t, tasks = setup(tmp_path / "2", ex2, 1)
    j2 = job(["a"], budget=1.0)  # not even the first fits
    tryit.run(j2, runner, t, root, CostModel({"with": 1.0, "without": 0.25}), tasks, WF)
    assert j2.results[0].status == "skipped" and not ex2.requests


def test_stop_ends_after_the_input_in_progress(tmp_path: Path):
    ex = Executor()
    runner, root, t, tasks = setup(tmp_path, ex, 3)
    j = job(["a", "b", "c"])
    real = ex.__call__

    def stop_after_first(req):
        out = real(req)
        j.stop.set()
        return out

    runner._executor = stop_after_first  # noqa: SLF001
    tryit.run(j, runner, t, root, CostModel({"with": 1.0, "without": 0.25}), tasks, WF)
    assert [r.status for r in j.results] == ["done", "stopped", "stopped"]
    assert j.status == "stopped" and len(ex.requests) == 1


def test_a_plain_skill_says_whether_it_was_opened(tmp_path: Path):
    ex = Executor(steps=())
    runner, root, t, tasks = setup(tmp_path, ex, 1, workflow=False)
    j = job(["a"])
    tryit.run(j, runner, t, root, CostModel({"with": 1.0, "without": 0.25}), tasks, None)
    assert j.results[0].steps == {"kind": "skill", "opened": False}
    assert ex.requests[0].prompt_template is None  # a plain skill is left to find, as in runs


def test_grading_is_off_by_default_and_one_call_per_answer_when_on(tmp_path: Path):
    calls = []

    def grader(task, answer):
        calls.append((task, answer))
        return task.startswith("refund"), "Offered the refund within 30 days."

    for grade in (False, True):
        ex = Executor()
        runner, root, t, tasks = setup(tmp_path / str(grade), ex, 2)
        j = job(["refund please", "cancel me"], grade=grade)
        costs = CostModel({"with": 1.0, "without": 0.25})
        tryit.run(j, runner, t, root, costs, tasks, WF, grader=grader)
        if not grade:
            assert calls == [] and all(r.grade is None for r in j.results)
            assert j.spent_usd == pytest.approx(0.6)
    assert len(calls) == 2
    a, b = j.results
    assert a.grade["followed"] is True and b.grade["followed"] is False
    assert a.grade["reason"] == "Offered the refund within 30 days."
    # Its own (stated) cost, counted against the budget.
    assert a.grade["cost_usd"] == tryit.T["judge_call_usd"]
    assert j.spent_usd == pytest.approx(0.6 + 2 * tryit.T["judge_call_usd"])


def test_a_grader_that_fails_leaves_the_answer_ungraded(tmp_path: Path):
    ex = Executor()
    runner, root, t, tasks = setup(tmp_path, ex, 1)
    j = job(["a"], grade=True)

    def broken(task, answer):
        raise RuntimeError("judge offline")

    tryit.run(j, runner, t, root, CostModel({"with": 1.0, "without": 0.25}), tasks, WF, broken)
    r = j.results[0]
    assert r.status == "done" and r.answer and "judge offline" in r.grade["error"]


def test_bounds():
    with pytest.raises(tryit.TryError):
        tryit.check_inputs([], 1)
    with pytest.raises(tryit.TryError):
        tryit.check_inputs(["a"] * (tryit.T["max_inputs"] + 1), 1)
    with pytest.raises(tryit.TryError, match="Input 2 is empty"):
        tryit.check_inputs(["a", "  "], 1)
    with pytest.raises(tryit.TryError, match="longer"):
        tryit.check_inputs(["x" * (tryit.T["max_input_chars"] + 1)], 1)
    with pytest.raises(tryit.TryError, match="budget"):
        tryit.check_inputs(["a"], 0)
    assert tryit.check_inputs([" a "], 1) == ["a"]


def test_price_is_the_budget_checks_with_trial_prediction():
    p = tryit.price(CostModel({"with": 1.0, "without": 0.25}), 4, 3.0, True, True)
    assert p["per_input"] == 1.25 and p["judge_per_input"] == tryit.T["judge_call_usd"]
    assert p["total_usd"] == pytest.approx(4 * (1.25 + tryit.T["judge_call_usd"]))
    assert p["inputs_in_budget"] == 2 and p["hard_cap"] is True


# ---------- the API ----------


@pytest.fixture
def api(tmp_path: Path, monkeypatch):
    ex = Executor()
    monkeypatch.setattr("proving_ground.runner.harbor.harbor_executor", ex)
    root = tmp_path / "proj"
    root.mkdir()
    (root / "app.py").write_text("x")
    sk = root / ".claude" / "skills" / "tone"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("---\nname: tone\ndescription: Be kind\n---\nBe kind.\n")
    creds = Credentials(env={}, home=tmp_path / "h")
    app = create_app(
        root,
        workspace=Workspace(tmp_path / "ws.json"),
        credentials=creds,
        home=tmp_path / "home",
        user_skills_dir=tmp_path / "skills",
        web_dist=tmp_path / "nodist",
        host_login=lambda: None,
    )
    c = TestClient(app, base_url=BASE)
    return SimpleNamespace(c=c, ex=ex, creds=creds, root=root, skill=sk, home=tmp_path / "home")


def wait(c, jid, until=lambda v: v["status"] != "running"):
    for _ in range(200):
        v = c.get(f"/api/try/{jid}").json()
        if until(v):
            return v
        time.sleep(0.02)
    raise AssertionError(v)


def test_price_first_with_no_sign_in(api):
    r = api.c.post(
        "/api/try/price", json={"workflow": WF, "n": 3, "budget_usd": 5, "grade": True},
        headers=ORIGIN,
    )  # fmt: skip
    p = r.json()
    assert r.status_code == 200 and p["inputs"] == 3 and p["hard_cap"] is True
    assert p["total_usd"] == pytest.approx(3 * (1.25 + tryit.T["judge_call_usd"]))
    assert p["gradable"] is True and "refund" in p["placeholder"]
    # A coding workflow: no grading offered, a bug report to paste.
    dev = {**WF, "discipline": "development"}
    p = api.c.post(
        "/api/try/price", json={"workflow": dev, "n": 1, "budget_usd": 5, "grade": True},
        headers=ORIGIN,
    ).json()  # fmt: skip
    assert p["gradable"] is False and p["judge_per_input"] == 0 and "Bug" in p["placeholder"]


def test_trying_needs_a_sign_in_and_a_cap(api):
    body = {"workflow": WF, "inputs": ["refund please"], "budget_usd": 2}
    r = api.c.post("/api/try", json=body, headers=ORIGIN)
    assert r.status_code == 400 and "Sign in" in r.json()["detail"]
    api.creds.set("codex", "api-key", "sk-test")
    r = api.c.post("/api/try", json=body | {"agent": "codex"}, headers=ORIGIN)
    assert r.status_code == 409 and "no hard cap" in r.json()["detail"]
    assert not api.ex.requests
    r = api.c.post(
        "/api/try", json=body | {"agent": "codex", "accept_no_cap": True}, headers=ORIGIN
    )
    assert r.status_code == 202 and r.json()["hard_cap"] is False
    wait(api.c, r.json()["id"])
    assert api.ex.requests[-1].max_cost_usd is None  # nothing to pass: Codex has no cap option


def test_bounds_are_checked_before_anything_runs(api):
    api.creds.set("claude-code", "api-key", "sk-test")
    for bad in (
        {"inputs": []},
        {"inputs": ["a"] * 6},
        {"inputs": ["a", " "]},
        {"inputs": ["x" * 9000]},
        {"inputs": ["a"], "budget_usd": 0},
        {"inputs": ["a"], "budget_usd": 51},
    ):
        body = {"workflow": WF, "budget_usd": 2} | bad
        assert api.c.post("/api/try", json=body, headers=ORIGIN).status_code == 422, bad
    both = {"workflow": WF, "skill_path": str(api.skill), "inputs": ["a"], "budget_usd": 2}
    assert api.c.post("/api/try", json=both, headers=ORIGIN).status_code == 422
    assert not api.ex.requests


def test_a_try_runs_reports_and_forgets(api):
    api.creds.set("claude-code", "api-key", "sk-test")
    body = {"workflow": WF, "inputs": ["Refund order 7?", "Cancel my plan"], "budget_usd": 4}
    r = api.c.post("/api/try", json=body, headers=ORIGIN)
    assert r.status_code == 202
    jid = r.json()["id"]
    v = wait(api.c, jid)
    assert v["status"] == "done" and v["inputs"] == ["Refund order 7?", "Cancel my plan"]
    assert [x["answer"] for x in v["results"]] == [
        "Reply to: Refund order 7?",
        "Reply to: Cancel my plan",
    ]
    assert v["results"][0]["steps"]["ran"] == 2 and v["spent_usd"] == pytest.approx(0.6)
    assert api.ex.requests[0].max_cost_usd == pytest.approx(4.0)
    assert not (api.home / "try" / jid).exists()  # the job's folder is gone when it ends
    assert api.c.delete(f"/api/try/{jid}", headers=ORIGIN).json() == {"forgotten": jid}
    assert api.c.get(f"/api/try/{jid}").status_code == 404


def test_one_try_at_a_time_and_stop(api, monkeypatch):
    api.creds.set("claude-code", "api-key", "sk-test")
    import threading

    gate = threading.Event()
    real = api.ex.__call__

    def slow(req):
        gate.wait(5)
        return real(req)

    monkeypatch.setattr("proving_ground.runner.harbor.harbor_executor", slow)
    body = {"workflow": WF, "inputs": ["a", "b", "c"], "budget_usd": 5}
    jid = api.c.post("/api/try", json=body, headers=ORIGIN).json()["id"]
    again = api.c.post("/api/try", json=body, headers=ORIGIN)
    assert again.status_code == 409 and "still going" in again.json()["detail"]
    assert api.c.delete(f"/api/try/{jid}", headers=ORIGIN).status_code == 409
    assert api.c.post(f"/api/try/{jid}/stop", headers=ORIGIN).json() == {"stopping": True}
    assert api.c.get(f"/api/try/{jid}").json()["stopping"] is True
    gate.set()
    v = wait(api.c, jid)
    assert v["status"] == "stopped"
    assert [x["status"] for x in v["results"]] == ["done", "stopped", "stopped"]


def test_a_repo_skill_runs_on_the_repo_and_an_input_can_be_kept_as_a_draft(api):
    api.creds.set("claude-code", "api-key", "sk-test")
    body = {"skill_path": str(api.skill), "inputs": ["Bug: Save twice makes two"], "budget_usd": 2}
    v = wait(api.c, api.c.post("/api/try", json=body, headers=ORIGIN).json()["id"])
    assert v["status"] == "done" and v["label"] == "tone"
    task = api.ex.requests[0].task_dir
    assert task.name == "try-1" and api.ex.requests[0].skills == (str(api.skill.resolve()),)
    r = api.c.post(
        "/api/scenarios/draft", json={"instruction": "Bug: Save twice makes two"}, headers=ORIGIN
    )
    assert r.status_code == 200
    s = next(x for x in load_scenarios(api.root) if x.id == r.json()["id"])
    assert s.instruction == "Bug: Save twice makes two" and s.check is None and not s.runnable
    again = api.c.post(
        "/api/scenarios/draft", json={"instruction": "Bug: Save twice makes two"}, headers=ORIGIN
    ).json()
    assert again["id"] == r.json()["id"] + "-2"


def test_grading_through_the_api_uses_the_cheapest_tier(api, monkeypatch):
    api.creds.set("claude-code", "api-key", "sk-test")
    seen = []

    class Judge:
        def __init__(self, _client=None):
            pass

        def call(self, prompt, tool, model, max_tokens):
            from proving_ground.generate.client import ToolCall

            seen.append(model)
            score = {"criterion": "goal", "score": 5, "evidence": "Offered the refund.\nMore."}
            return ToolCall({"scores": [score]}, "tool_use", 10, 5)

    monkeypatch.setattr("proving_ground.api.app.AnthropicClient", Judge)
    body = {"workflow": WF, "inputs": ["refund"], "budget_usd": 2, "grade": True,
            "goal": "Refunds within 30 days, else a kind no."}  # fmt: skip
    v = wait(api.c, api.c.post("/api/try", json=body, headers=ORIGIN).json()["id"])
    g = v["results"][0]["grade"]
    assert g == {"followed": True, "reason": "Offered the refund.", "cost_usd": 0.01}
    assert seen == [tryit.T["judge_model"]] == ["claude-haiku-5-5"]
    # Not offered for a coding workflow: ticking it does nothing, and no judge is called.
    dev = body | {"workflow": {**WF, "discipline": "development"}}
    v = wait(api.c, api.c.post("/api/try", json=dev, headers=ORIGIN).json()["id"])
    assert v["grade"] is False and v["results"][0]["grade"] is None and len(seen) == 1


def test_the_runner_is_a_real_harbor_runner(tmp_path: Path):
    ex = Executor()
    runner, *_ = setup(tmp_path, ex, 1)
    assert isinstance(runner, HarborRunner) and runner.caps_cost


def test_the_example_input_follows_the_goal():
    # A support goal: a customer email that tests the limit the goal sets ($500 -> $625).
    sup = tryit.goal_example(
        "A support agent that answers tickets from our policy docs and hands refunds over $500 "
        "to a person.",
        "research",
    )
    assert sup["kind"] == "support" and "$625" in sup["example"] and "refund" in sup["example"]
    # A docs Q&A goal: a question the docs should answer, whatever the workflow's discipline.
    docs = tryit.goal_example("A Q&A agent that answers questions about our docs.", "research")
    assert docs["kind"] == "docs" and docs["example"].endswith("say so.")
    assert "EU" not in docs["example"]
    # A coding goal: a bug report. No goal: the discipline's placeholder, as before.
    code = tryit.goal_example(
        "Fix refund bugs without breaking the plan limits; run the tests.", None
    )
    assert code["kind"] == "coding" and code["example"].startswith("Bug:")
    assert tryit.goal_example("", "research")["example"] == tryit.placeholder("research")
    # Deterministic: the same goal, the same example.
    assert tryit.goal_example("support tickets", None) == tryit.goal_example(
        "support tickets", None
    )


def test_try_example_and_price_say_what_runs(api):
    r = api.c.post(
        "/api/try/example",
        json={"goal": "Answer questions from the docs.", "discipline": "research"},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "docs"
    p = api.c.post(
        "/api/try/price", json={"workflow": WF, "n": 1, "budget_usd": 2}, headers=ORIGIN
    ).json()
    assert p["steps"] == 3 and p["model_label"] == "Sonnet 5.5"


def test_a_try_is_priced_from_what_earlier_tries_of_it_cost(api):
    """Each input's cost is remembered (only the amount) and the next price starts from it, not
    from any workflow's bench trials."""
    api.creds.set("claude-code", "api-key", "sk-test")
    ask = {"workflow": WF, "n": 1, "budget_usd": 5}
    before = api.c.post("/api/try/price", json=ask, headers=ORIGIN).json()
    r = api.c.post(
        "/api/try", json={"workflow": WF, "inputs": ["Refund order 7?"], "budget_usd": 4},
        headers=ORIGIN,
    )  # fmt: skip
    wait(api.c, r.json()["id"])
    after = api.c.post("/api/try/price", json=ask, headers=ORIGIN).json()
    assert after["source"] == "measured on 1 earlier trial" and after["per_input"] >= 0.3
    assert after["per_input"] != before["per_input"]
    saved = json.loads((api.home / "try-costs.json").read_text())
    assert [v for v in saved.values()] == [[0.3]]  # amounts only: no input, no answer
