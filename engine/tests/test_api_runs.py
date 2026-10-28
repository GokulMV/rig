import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from proving_ground.api.app import create_app
from proving_ground.files import save_scenario
from proving_ground.models import Scenario

BASE = "http://127.0.0.1:7357"
ORIGIN = {"origin": BASE}


def fake_result(reward):
    return SimpleNamespace(
        exception_info=None,
        verifier_result=SimpleNamespace(rewards={"reward": reward}),
        agent_result=SimpleNamespace(n_input_tokens=10, n_output_tokens=5, cost_usd=0.5),
        started_at=None,
        finished_at=None,
        trial_name="t",
    )


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    root = tmp_path / "proj"
    root.mkdir()
    (root / "app.py").write_text("x")
    save_scenario(root, Scenario(id="a", instruction="Fix.", check="true", check_status="approved"))
    sk = tmp_path / "skills" / "tdd"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("---\nname: tdd\n---\nTest first.\n")
    return root, sk


def events(c: TestClient, eid: int) -> list[dict]:
    out = []
    with c.stream("GET", f"/api/experiments/{eid}/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
    return out


def test_start_and_follow_an_experiment(env, monkeypatch):
    root, sk = env
    monkeypatch.setattr(
        "proving_ground.runner.harbor.harbor_executor",
        lambda req: fake_result(0.0 if req.agent == "nop" else (1.0 if req.skills else 0.0)),
    )
    c = TestClient(create_app(root), base_url=BASE)
    body = {"treatment_path": str(sk), "n": 6, "budget": 100}
    r = c.post("/api/experiments", json=body, headers=ORIGIN)
    assert r.status_code == 200, r.text
    started = r.json()
    assert started["id"] == 1 and started["repeats"] == 6 and started["trials"] == 12
    evs = events(c, 1)
    assert [e["type"] for e in evs][-1] == "finished"
    assert sum(e["type"] == "trial" for e in evs) == 12
    assert evs[-1]["summary"]["verdict"] == "helps"
    again = events(c, 1)  # replayed after the run ended
    assert again == evs
    assert c.get("/api/experiments/1").json()["status"] == "done"


def test_one_run_at_a_time_and_errors(env, monkeypatch):
    root, sk = env
    gate = threading.Event()

    def slow(req):
        if req.agent == "nop":
            return fake_result(0.0)
        gate.wait(5)
        return fake_result(1.0)

    monkeypatch.setattr("proving_ground.runner.harbor.harbor_executor", slow)
    c = TestClient(create_app(root), base_url=BASE)
    body = {"treatment_path": str(sk), "n": 2, "budget": 100}
    assert c.post("/api/experiments", json=body, headers=ORIGIN).status_code == 200
    busy = c.post("/api/experiments", json=body, headers=ORIGIN)
    assert busy.status_code == 409 and "experiment 1 is still running" in busy.json()["detail"]
    gate.set()
    assert events(c, 1)[-1]["type"] == "finished"

    bad = c.post("/api/experiments", json=body | {"treatment_path": str(root)}, headers=ORIGIN)
    assert bad.status_code == 422 and "SKILL.md" in bad.json()["detail"]
    zero = c.post("/api/experiments", json=body | {"budget": 0}, headers=ORIGIN)
    assert zero.status_code == 422
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert c.post("/api/experiments", json=body, headers=ORIGIN).status_code == 400


def test_run_errors_arrive_as_an_event(env, monkeypatch):
    root, sk = env
    monkeypatch.setattr(
        "proving_ground.runner.harbor.harbor_executor", lambda req: fake_result(1.0)
    )  # the check passes with no agent: preflight must stop the run
    c = TestClient(create_app(root), base_url=BASE)
    c.post("/api/experiments", json={"treatment_path": str(sk), "budget": 5}, headers=ORIGIN)
    last = events(c, 1)[-1]
    assert last["type"] == "error" and "pass with no agent" in last["detail"]


def test_events_for_an_experiment_that_is_not_running(env):
    root, _ = env
    c = TestClient(create_app(root), base_url=BASE)
    assert events(c, 7) == [{"type": "idle"}]


def test_a_running_repo_experiment_shows_in_the_top_bar_and_can_be_stopped(env, monkeypatch):
    root, sk = env
    gate = threading.Event()

    def slow(req):
        gate.wait(5)
        return fake_result(0.0 if req.agent == "nop" else 1.0)

    monkeypatch.setattr("proving_ground.runner.harbor.harbor_executor", slow)
    c = TestClient(create_app(root), base_url=BASE)
    assert c.get("/api/runs/active").json() == {"running": None}
    assert c.post("/api/experiments/1/stop", headers=ORIGIN).status_code == 404
    c.post(
        "/api/experiments", json={"treatment_path": str(sk), "n": 6, "budget": 100}, headers=ORIGIN
    )
    going = c.get("/api/runs/active").json()["running"]
    assert going["kind"] == "repo" and going["id"] == 1 and going["treatment"] == "tdd"
    assert going["repo_name"] == root.name and going["budget_usd"] == 100
    assert c.post("/api/experiments/1/stop", headers=ORIGIN).json() == {"stopping": True}
    gate.set()
    evs = events(c, 1)
    assert evs[-1]["type"] == "finished"
    assert c.get("/api/experiments/1").json()["status"] == "stopped"
    assert sum(e["type"] == "trial" for e in evs) < 12
    assert c.get("/api/runs/active").json() == {"running": None}


def test_a_run_left_running_by_a_restart_shows_as_stopped(env, monkeypatch):
    root, sk = env
    monkeypatch.setattr(
        "proving_ground.runner.harbor.harbor_executor", lambda req: fake_result(1.0)
    )
    c = TestClient(create_app(root), base_url=BASE)
    c.post(
        "/api/experiments", json={"treatment_path": str(sk), "n": 1, "budget": 100}, headers=ORIGIN
    )
    events(c, 1)
    from proving_ground.store import Store

    Store.for_project(root).set_status(1, "running")  # as a killed server leaves it
    fresh = TestClient(create_app(root), base_url=BASE)
    assert fresh.get("/api/experiments").json()[0]["status"] == "stopped"


def test_a_run_is_priced_before_it_starts_and_before_sign_in(env, monkeypatch):
    """trial-budget: the Measure step shows the budget check's own prediction up front."""
    from proving_ground import skills
    from proving_ground.budget import prior_usd

    root, sk = env
    monkeypatch.delenv("ANTHROPIC_API_KEY")  # nothing signed in: the estimate still answers
    monkeypatch.setattr(
        "proving_ground.runner.harbor.harbor_executor",
        lambda req: fake_result(1.0 if req.skills else 0.0),
    )
    c = TestClient(create_app(root), base_url=BASE)
    margin = skills.load("trial-budget").values["margin"]
    rid = c.get("/api/repos").json()[0]["id"]
    body = {
        "pairs": 4,
        "repo": rid,
        "treatment_path": str(sk),
        "model": "claude-sonnet-5-5",
        "budget": 2,
    }
    first = c.post("/api/runs/estimate", json=body, headers=ORIGIN).json()
    prior = prior_usd("claude-sonnet-5-5")
    assert first["trials"] == 8 and first["source"]["with"].startswith("a first guess")
    assert first["per_trial"]["with"] == round(prior["with"] * margin, 4)
    assert first["total_usd"] == round(4 * (prior["with"] + prior["without"]) * margin, 4)
    assert first["pairs_in_budget"] == int(2 // ((prior["with"] + prior["without"]) * margin))
    # A local model costs nothing.
    free = c.post("/api/runs/estimate", json=body | {"local": True}, headers=ORIGIN).json()
    assert free["total_usd"] == 0 and free["free"] and free["pairs_in_budget"] == 4

    # After a run in this repo, its trials ($0.50 each here) are the evidence.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    c.post(
        "/api/experiments", json={"treatment_path": str(sk), "n": 2, "budget": 100}, headers=ORIGIN
    )
    events(c, 1)
    after = c.post("/api/runs/estimate", json=body, headers=ORIGIN).json()
    assert after["source"]["with"] == "measured on 2 earlier trials"
    assert after["measured_trials"] == {"with": 2, "without": 2}
    assert after["per_trial"]["with"] == round(0.5 * margin, 4)
    # What it takes to tell the target from noise, and the full-run-no-better-than-pilot warning.
    full = c.post(
        "/api/runs/estimate", json=body | {"pairs": 21, "pilot_pairs": 3}, headers=ORIGIN
    ).json()
    assert full["sizing"]["pairs"] == 31 and full["sizing"]["usd"] == 39.0  # 31 x $1.25
    assert full["pairs_in_budget"] == 1
    assert full["no_better_than_pilot"] == (
        "At $2.00 this full run stops after 1 pair: no more conclusive than the pilot."
    )
    # The size choice's "Full" label, asked for alongside a pilot's estimate.
    pilot = c.post(
        "/api/runs/estimate",
        json=body | {"pairs": 3, "pilot_pairs": 3, "full_pairs": 21},
        headers=ORIGIN,
    ).json()
    assert pilot["full"]["text"] == "Full · the budget only covers 1 pair, as many as the pilot"
    assert pilot["no_better_than_pilot"] is None  # the pilot itself
    big = c.post(
        "/api/runs/estimate",
        json=body | {"pairs": 3, "pilot_pairs": 3, "full_pairs": 31, "budget": 39},
        headers=ORIGIN,
    ).json()
    assert big["full"]["text"] == "Full · 31 pairs · conclusive to ±25 pts"
    # One repo, a size and its tasks: the engine plans the pairs. A full run grows with the
    # budget up to the sizing, and starting it plans the same pairs.
    one = body | {"pairs": 1, "size": "full", "tasks": 1}
    low = c.post("/api/runs/estimate", json=one, headers=ORIGIN).json()
    assert low["pairs"] == 20 and low["sizing"]["enough_planned"]
    sized = c.post(
        "/api/runs/estimate", json=one | {"budget": low["sizing"]["usd"]}, headers=ORIGIN
    ).json()
    assert sized["pairs"] == 31 and sized["pairs_in_budget"] == 31
    assert sized["full"]["text"] == "Full · 31 pairs · conclusive to ±25 pts"
    pilot = c.post("/api/runs/estimate", json=one | {"size": "pilot"}, headers=ORIGIN).json()
    assert pilot["pairs"] == 1 and pilot["full"] == low["full"]
    started = c.post(
        "/api/experiments",
        json={
            "treatment_path": str(sk),
            "n": 20,
            "size": "full",
            "scenario_ids": ["a"],
            "model": "claude-sonnet-5-5",
            "budget": low["sizing"]["usd"],
        },
        headers=ORIGIN,
    ).json()
    assert started["repeats"] == 31 and started["trials"] == 62
    events(c, started["id"])
    assert c.get("/api/experiments").json()[0]["status_text"] == "Done"
    assert (
        c.post("/api/runs/estimate", json=body | {"repo": "nope"}, headers=ORIGIN).status_code
        == 404
    )
    assert (
        c.post("/api/runs/estimate", json=body | {"agent": "nope"}, headers=ORIGIN).status_code
        == 422
    )


def test_repo_runs_list_their_agent_and_pairs_and_can_be_forgotten(env, monkeypatch):
    root, sk = env
    monkeypatch.setattr(
        "proving_ground.runner.harbor.harbor_executor",
        lambda req: fake_result(1.0 if req.skills else 0.0),
    )
    c = TestClient(create_app(root), base_url=BASE)
    c.post(
        "/api/experiments", json={"treatment_path": str(sk), "n": 2, "budget": 100}, headers=ORIGIN
    )
    events(c, 1)
    [row] = c.get("/api/experiments").json()
    assert row["agent"] == "claude-code" and row["n_pairs"] == 2 and row["budget_usd"] == 100
    assert c.delete("/api/experiments/9", headers=ORIGIN).status_code == 404
    assert c.delete("/api/experiments/1", headers=ORIGIN).json() == {"removed": 1}
    assert c.get("/api/experiments").json() == []
