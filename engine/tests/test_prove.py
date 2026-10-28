"""Prove check: a generated check must fail on the untouched repo, with no agent."""

import time
from pathlib import Path
from types import SimpleNamespace

from test_api_workspace import BASE, ORIGIN, FakeCli
from test_catalog import FakeGitHub

import proving_ground.runner.harbor as harbor
from proving_ground.agents import Credentials
from proving_ground.api.app import create_app
from proving_ground.files import save_scenario
from proving_ground.models import Scenario
from proving_ground.workspace import Workspace


def _client(tmp_path: Path, monkeypatch, fake):
    from fastapi.testclient import TestClient

    repo = tmp_path / "shop"
    repo.mkdir()
    (repo / "README.md").write_text("A shop\n")
    monkeypatch.setattr(harbor, "harbor_executor", fake)
    c = TestClient(
        create_app(
            workspace=Workspace(tmp_path / "ws.json"),
            credentials=Credentials(env={}, home=tmp_path / "h"),
            github=FakeGitHub(),
            home=tmp_path / "home",
            user_skills_dir=tmp_path / "none",
            web_dist=tmp_path / "nodist",
            host_login=lambda: None,
            cli_model=FakeCli,
        ),
        base_url=BASE,
    )
    assert c.post("/api/repos", json={"path": str(repo)}, headers=ORIGIN).status_code == 200
    save_scenario(
        repo,
        Scenario(id="refund", title="Refund", instruction="Do it.", check="bash /tests/c.sh"),
    )
    return c


def _result(reward=0.0, exc=None):
    return SimpleNamespace(
        exception_info=exc,
        verifier_result=SimpleNamespace(rewards={"reward": reward}),
        agent_result=None,
        started_at=None,
        finished_at=None,
        trial_name="fake",
    )


def _finish(c):
    for _ in range(100):
        r = c.get("/api/scenarios/refund/prove", headers=ORIGIN).json()
        if r["status"] != "running":
            return r
        time.sleep(0.05)
    raise AssertionError("prove never finished")


def test_idle_before_any_run(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, lambda req: _result())
    assert c.get("/api/scenarios/refund/prove", headers=ORIGIN).json()["status"] == "idle"


def test_proven_when_check_fails_untouched(tmp_path, monkeypatch):
    seen = []

    def fake(req):
        seen.append(req.agent)
        return _result(0.0)

    c = _client(tmp_path, monkeypatch, fake)
    assert c.post("/api/scenarios/refund/prove", headers=ORIGIN).json() == {"status": "running"}
    r = _finish(c)
    assert r["status"] == "done" and r["proven"] is True
    assert seen == ["nop"]


def test_broken_when_check_passes_untouched(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, lambda req: _result(1.0))
    c.post("/api/scenarios/refund/prove", headers=ORIGIN)
    r = _finish(c)
    assert r["status"] == "done" and r["proven"] is False


def test_error_when_the_sandbox_cannot_build(tmp_path, monkeypatch):
    exc = SimpleNamespace(exception_type="BuildError", exception_message="docker build failed")
    c = _client(tmp_path, monkeypatch, lambda req: _result(exc=exc))
    c.post("/api/scenarios/refund/prove", headers=ORIGIN)
    r = _finish(c)
    assert r["status"] == "error" and r["proven"] is None
    assert "docker build failed" in r["detail"]


def test_error_when_the_executor_raises(tmp_path, monkeypatch):
    def boom(req):
        raise RuntimeError("no docker")

    c = _client(tmp_path, monkeypatch, boom)
    c.post("/api/scenarios/refund/prove", headers=ORIGIN)
    r = _finish(c)
    assert r["status"] == "error" and "no docker" in r["detail"]


def test_unknown_scenario_is_404(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, lambda req: _result())
    assert c.post("/api/scenarios/nope/prove", headers=ORIGIN).status_code == 404
