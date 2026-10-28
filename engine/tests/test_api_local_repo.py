"""A repo's run on Measure on a local model, as the Lab's runs: Claude Code pointed at the local
server, no sign-in and no cost, a longer time limit, the skill handed over, and the run's record
naming the model. Skill runs, before/after runs and metric runs alike; Harbor is faked."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_before_after import make_repo

from proving_ground import local_models as lm
from proving_ground.agents import Credentials
from proving_ground.api.app import create_app
from proving_ground.files import save_scenario
from proving_ground.models import Scenario
from proving_ground.store import Store

BASE = "http://127.0.0.1:7357"
ORIGIN = {"origin": BASE}
R = lm.L["repo"]


def result(reward: float, tokens: int = 1000):
    # The fake agent reports a cost: a local run must still count it as nothing.
    return SimpleNamespace(
        exception_info=None,
        verifier_result=SimpleNamespace(rewards={"reward": reward}),
        agent_result=SimpleNamespace(n_input_tokens=tokens, n_output_tokens=0, cost_usd=0.5),
        started_at=None,
        finished_at=None,
        trial_name="t",
    )


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    """A repo with two tasks, a skill, a local model that speaks Anthropic's API and one that
    doesn't, and no sign-in at all."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    root = make_repo(tmp_path / "repo")
    # Not committed: a run snapshots the working tree, a before/after run each commit.
    save_scenario(root, Scenario(id="b", instruction="Fix.", check="true", check_status="approved"))
    sk = tmp_path / "skills" / "tdd"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("---\nname: tdd\n---\nTest first.\n")
    home = tmp_path / "home"
    reg = lm.Registry(home / "local-models.json")
    m = lm.make("http://127.0.0.1:11434", "qwen3:8b", "ollama")
    m = reg.add(lm.LocalModel(m.id, m.label, m.base, m.model, m.kind, True))
    plain = reg.add(lm.make("http://127.0.0.1:1234", "phi-4", "lmstudio"))
    calls: list = []

    def fake(req):
        calls.append(req)
        if req.agent == "nop":
            return result(0.0, 0)
        # Every trial passes; the change (a skill, or the after side's code) uses a third of
        # the tokens.
        return result(1.0, 500 if req.skills or req.task_dir.parent.name == "tasks-with" else 1500)

    monkeypatch.setattr("proving_ground.runner.harbor.harbor_executor", fake)
    app = create_app(root, home=home, credentials=Credentials(env={}, home=tmp_path / "h"))
    c = TestClient(app, base_url=BASE)
    return SimpleNamespace(c=c, root=root, sk=sk, m=m, plain=plain, calls=calls)


def run(c: TestClient, body: dict) -> dict:
    r = c.post("/api/experiments", json=body, headers=ORIGIN)
    assert r.status_code == 200, r.text
    started = r.json()
    with c.stream("GET", f"/api/experiments/{started['id']}/events") as s:
        last = [line for line in s.iter_lines() if line.startswith("data: ")][-1]
    assert json.loads(last[6:])["type"] == "finished", last
    return started


def meta(root: Path, eid: int) -> dict:
    return json.loads((root / ".proving-ground" / "runs" / str(eid) / "meta.json").read_text())


def agent_calls(calls: list) -> list:
    return [q for q in calls if q.agent == "claude-code"]


def test_a_skill_runs_on_a_local_model_with_no_sign_in(env):
    c, m = env.c, env.m
    body = {"treatment_path": str(env.sk), "n": 2, "budget": 1, "scenario_ids": ["a", "b"]}
    # Without a local model this needs a sign-in, as before.
    r = c.post("/api/experiments", json=body, headers=ORIGIN)
    assert r.status_code == 400 and "Sign in" in r.json()["detail"]

    started = run(c, body | {"local_model": m.id})
    assert started["model"] == m.id
    assert started["local_model"] == {"id": m.id, "label": "qwen3:8b · ollama"}
    q = agent_calls(env.calls)
    assert q, "the agent never ran"
    e = dict(q[0].env)
    assert e["ANTHROPIC_BASE_URL"] == "http://host.docker.internal:11434"
    assert e["ANTHROPIC_API_KEY"] == "local"
    # Harbor asks the server for its own model id; only the host is reachable from the sandbox.
    assert {x.model for x in q} == {"qwen3:8b"} and q[0].hosts == ("host.docker.internal",)
    toml = (Path(q[0].task_dir) / "task.toml").read_text()
    assert f"[agent]\ntimeout_sec = {600 * lm.L['timeout_factor']}" in toml
    # A small model never opens a skill it is only offered: the "with" arm is told to.
    with_arm = [x for x in q if x.skills]
    assert with_arm and all(x.prompt_template is not None for x in with_arm)
    got = meta(env.root, started["id"])
    assert got["local_model"] == m.id and got["local_label"] == "qwen3:8b · ollama"
    assert got["nudge_prompt"] is True and got["model"] == m.id

    d = c.get(f"/api/experiments/{started['id']}").json()
    assert d["local_model"] == {"id": m.id, "label": "qwen3:8b · ollama"}
    assert d["spent_usd"] == 0  # the fake agent says $0.50 a trial: free all the same
    cost = next(p for p in d["rig"]["parts"] if p["id"] == "cost")
    assert cost["score"] == 100
    row = next(x for x in c.get("/api/experiments").json() if x["id"] == started["id"])
    assert row["local_model"]["label"] == "qwen3:8b · ollama" and row["model"] == m.id


def test_a_run_on_the_signed_in_agent_records_no_local_model(env, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    c = TestClient(create_app(env.root, home=env.root.parent / "home"), base_url=BASE)
    started = run(c, {"treatment_path": str(env.sk), "n": 2, "budget": 100})
    assert started["local_model"] is None
    assert "local_model" not in meta(env.root, started["id"])
    assert c.get(f"/api/experiments/{started['id']}").json()["local_model"] is None
    assert all(not dict(q.env).get("ANTHROPIC_BASE_URL") for q in agent_calls(env.calls))


def test_unticked_the_skill_is_left_to_be_found(env):
    started = run(
        env.c,
        {"treatment_path": str(env.sk), "n": 2, "budget": 1, "local_model": env.m.id}
        | {"nudge_prompt": False},
    )
    assert meta(env.root, started["id"])["nudge_prompt"] is False
    assert all(x.prompt_template is None for x in agent_calls(env.calls))


def test_refusals_unknown_model_no_anthropic_api_and_cost(env):
    c = env.c
    body = {"treatment_path": str(env.sk), "n": 2, "budget": 1}
    r = c.post("/api/experiments", json=body | {"local_model": "local:nope"}, headers=ORIGIN)
    assert r.status_code == 404
    r = c.post("/api/experiments", json=body | {"local_model": env.plain.id}, headers=ORIGIN)
    assert r.status_code == 422 and "Anthropic's Messages API" in r.json()["detail"]
    r = c.post(
        "/api/experiments",
        json=body | {"local_model": env.m.id, "agent": "codex"},
        headers=ORIGIN,
    )
    assert r.status_code == 422
    r = c.post(
        "/api/experiments",
        json=body | {"local_model": env.m.id, "metric": "cost"},
        headers=ORIGIN,
    )
    assert r.status_code == 422 and r.json()["detail"] == R["cost_metric"]
    assert c.get("/api/experiments").json() == []  # nothing was written
    assert not env.calls


def test_a_code_change_before_and_after_on_a_local_model(env):
    started = run(
        env.c,
        {"before_after": {"base": "HEAD", "after": "split"}, "n": 2, "budget": 1}
        | {"local_model": env.m.id},
    )
    q = agent_calls(env.calls)
    assert {x.task_dir.parent.name for x in q} == {"tasks", "tasks-with"}
    assert all(dict(x.env)["ANTHROPIC_BASE_URL"].endswith(":11434") for x in q)
    assert meta(env.root, started["id"])["nudge_prompt"] is None  # no skill to hand over
    d = env.c.get(f"/api/experiments/{started['id']}").json()
    assert d["treatment_kind"] == "before_after" and d["local_model"]["id"] == env.m.id
    assert d["spent_usd"] == 0


def test_a_run_scored_on_tokens_on_a_local_model(env):
    started = run(
        env.c,
        {"treatment_path": str(env.sk), "n": 4, "budget": 1, "metric": "tokens"}
        | {"local_model": env.m.id},
    )
    assert started["metric"] == "tokens"
    m = meta(env.root, started["id"])
    assert m["metric"] == "tokens" and m["local_model"] == env.m.id
    d = env.c.get(f"/api/experiments/{started['id']}").json()
    assert d["rig"]["metric"]["id"] == "tokens"
    assert d["rig"]["metric"]["ratio"] == pytest.approx(1 / 3)


def test_a_full_run_is_free_and_grows_to_the_sizing(env):
    """Priced as free, a full run plans the pairs the sizing wants, as the estimate says."""
    est = env.c.post(
        "/api/runs/estimate",
        json={"pairs": 2, "local": True, "size": "full", "tasks": 2, "budget": 1},
        headers=ORIGIN,
    ).json()
    assert est["free"] is True and est["total_usd"] == 0
    assert est["pairs"] > 2  # free: the budget doesn't hold it to the pilot
    started = run(
        env.c,
        {"treatment_path": str(env.sk), "budget": 1, "local_model": env.m.id}
        | {"size": "full", "scenario_ids": ["a", "b"]},
    )
    assert started["trials"] == 2 * est["pairs"]


def test_a_resumed_run_goes_on_on_its_local_model(env):
    first = run(
        env.c, {"treatment_path": str(env.sk), "n": 2, "budget": 1, "local_model": env.m.id}
    )
    Store.for_project(env.root).set_repeats(first["id"], 2)  # one more repeat left to run
    env.calls.clear()
    # The request names no local model: the run's own is used, not a sign-in.
    run(env.c, {"treatment_path": str(env.sk), "budget": 1, "resume": first["id"]})
    assert agent_calls(env.calls)
    assert all(dict(x.env)["ANTHROPIC_API_KEY"] == "local" for x in agent_calls(env.calls))


def test_the_local_models_list_carries_measures_words(env):
    got = env.c.get("/api/local-models").json()
    assert got["repo"] == R and got["timeout_factor"] == lm.L["timeout_factor"]
