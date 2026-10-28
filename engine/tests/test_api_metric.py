"""A run's metric through the API: chosen on Measure, kept in the run's meta.json, defaulted from
the goal's hint, and scored on in the run's Rig score."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from proving_ground.api.app import create_app
from proving_ground.files import save_scenario
from proving_ground.models import Scenario
from proving_ground.store import Store

BASE = "http://127.0.0.1:7357"
ORIGIN = {"origin": BASE}


def result(reward, tokens):
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
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    root = tmp_path / "proj"
    root.mkdir()
    (root / "app.py").write_text("x")
    for sid in ("a", "b", "c", "d"):
        save_scenario(
            root, Scenario(id=sid, instruction="Fix.", check="true", check_status="approved")
        )
    sk = tmp_path / "skills" / "ponytail"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("---\nname: ponytail\n---\nSay less.\n")
    calls = {"n": 0}

    def fake(req):
        if req.agent == "nop":
            return result(0.0, 0)
        calls["n"] += 1
        # Same pass rate both ways; a third of the tokens with the skill, with some spread.
        spread = 1 + (calls["n"] % 5) / 10
        return result(1.0, int((10_000 if req.skills else 30_000) * spread))

    monkeypatch.setattr("proving_ground.runner.harbor.harbor_executor", fake)
    return root, sk


def run(c: TestClient, body: dict) -> dict:
    r = c.post("/api/experiments", json=body, headers=ORIGIN)
    assert r.status_code == 200, r.text
    started = r.json()
    with c.stream("GET", f"/api/experiments/{started['id']}/events") as s:
        for _ in s.iter_lines():
            pass
    return started


def meta(root: Path, eid: int) -> dict:
    return json.loads((root / ".proving-ground" / "runs" / str(eid) / "meta.json").read_text())


def test_a_token_run_is_kept_and_scored_on_tokens(env):
    root, sk = env
    c = TestClient(create_app(root), base_url=BASE)
    started = run(c, {"treatment_path": str(sk), "n": 12, "budget": 100, "metric": "tokens"})
    assert started["metric"] == "tokens"
    assert meta(root, started["id"])["metric"] == "tokens"
    got = c.get(f"/api/experiments/{started['id']}").json()
    assert got["metric"] == "tokens"
    m = got["rig"]["metric"]
    assert m["id"] == "tokens" and m["ratio"] == pytest.approx(1 / 3, rel=0.15)
    assert m["headline"].startswith("Tokens per Solved Task: with ")
    # 12 pairs that all pass both ways: the guard isn't met yet, so no cut is claimed.
    assert m["noninferior"] is False
    assert got["rig"]["band"] == "not_proven"
    assert next(p for p in got["rig"]["parts"] if p["id"] == "lift")["score"] == 0
    row = next(e for e in c.get("/api/experiments").json() if e["id"] == started["id"])
    assert row["metric"] == "tokens" and row["rig"]["metric"]["id"] == "tokens"


def test_the_pass_rate_is_the_default_and_an_old_run_reads_as_one(env):
    root, sk = env
    c = TestClient(create_app(root), base_url=BASE)
    started = run(c, {"treatment_path": str(sk), "n": 4, "budget": 100})
    assert meta(root, started["id"])["metric"] == "pass_rate"
    got = c.get(f"/api/experiments/{started['id']}").json()
    assert got["metric"] == "pass_rate" and "metric" not in got["rig"]
    # A run from before the choice existed has no `metric` in its meta.json.
    m = meta(root, started["id"])
    m.pop("metric")
    (root / ".proving-ground" / "runs" / str(started["id"]) / "meta.json").write_text(
        json.dumps(m)
    )
    assert c.get(f"/api/experiments/{started['id']}").json()["metric"] == "pass_rate"


def test_the_goal_hint_is_the_default(env):
    root, sk = env
    c = TestClient(create_app(root), base_url=BASE)
    store = Store.for_project(root)
    pid = store.ensure_project(str(root.resolve()))
    store.add_source(pid, "usecase", "use-case", "Cut the token use 3x.", {"metric": "tokens"})
    assert c.get("/api/project").json()["goal_metric"] == "tokens"
    started = run(c, {"treatment_path": str(sk), "n": 4, "budget": 100})
    assert meta(root, started["id"])["metric"] == "tokens"
    # The choice on Measure wins over the hint.
    again = run(c, {"treatment_path": str(sk), "n": 4, "budget": 100, "metric": "pass_rate"})
    assert meta(root, again["id"])["metric"] == "pass_rate"
    # A hint that isn't a metric is ignored.
    store.add_source(pid, "usecase", "use-case", "Cut it.", {"metric": "vibes"})
    assert c.get("/api/project").json()["goal_metric"] is None


def test_an_unknown_metric_is_refused(env):
    root, sk = env
    c = TestClient(create_app(root), base_url=BASE)
    r = c.post(
        "/api/experiments",
        json={"treatment_path": str(sk), "n": 4, "budget": 100, "metric": "vibes"},
        headers=ORIGIN,
    )
    assert r.status_code == 422


def test_the_estimate_sizes_a_saving_for_the_guard(env):
    root, sk = env
    c = TestClient(create_app(root), base_url=BASE)
    base = {"pairs": 4, "agent": "claude-code", "treatment_path": str(sk), "tasks": 4}
    pilot = c.post(
        "/api/runs/estimate", json=base | {"size": "pilot", "budget": 5, "metric": "tokens"}, headers=ORIGIN
    ).json()
    assert pilot["metric_plan"]["enough"] is False
    assert pilot["metric_plan"]["need_pairs"] == 39
    plain = c.post("/api/runs/estimate", json=base | {"size": "full", "budget": 10_000}, headers=ORIGIN).json()
    assert "metric_plan" not in plain
    full = c.post(
        "/api/runs/estimate", json=base | {"size": "full", "budget": 10_000, "metric": "tokens"}, headers=ORIGIN
    ).json()
    # A full run on tokens grows to the guard's pairs, in whole repeats of the 4 tasks.
    assert full["pairs"] == 40 > plain["pairs"]
    assert full["metric_plan"]["enough"] is True


def test_a_full_run_on_tokens_plans_the_guards_pairs(env):
    root, sk = env
    c = TestClient(create_app(root), base_url=BASE)
    r = c.post(
        "/api/experiments",
        json={
            "treatment_path": str(sk), "n": 4, "budget": 10_000, "size": "full",
            "scenario_ids": ["a", "b", "c", "d"], "metric": "tokens",
        },
        headers=ORIGIN,
    )  # fmt: skip
    assert r.status_code == 200, r.text
    assert r.json()["repeats"] * 4 == 40
    c.post(f"/api/experiments/{r.json()['id']}/stop", headers=ORIGIN)
