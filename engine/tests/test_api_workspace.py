import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_catalog import FakeGitHub

from proving_ground.agents import Credentials
from proving_ground.api.app import create_app
from proving_ground.workspace import Workspace

BASE = "http://127.0.0.1:7357"
ORIGIN = {"origin": BASE}


class FakeCli:
    """Stands in for `claude -p`: tests never call a real model."""

    def call(self, prompt, tool, model, max_tokens):
        from proving_ground.generate.client import ToolCall

        return ToolCall(
            {"low": -5, "high": 9, "likely": 3, "confidence": "low", "reason": "x"},
            "tool_use",
            1,
            1,
        )


@pytest.fixture
def env(tmp_path: Path):
    a = tmp_path / "shop"
    (a / "src" / "shop" / "api").mkdir(parents=True)
    (a / "src" / "shop" / "api" / "__init__.py").write_text("from shop.db import x\n")
    (a / "src" / "shop" / "db").mkdir()
    (a / "src" / "shop" / "db" / "__init__.py").write_text("")
    (a / "pyproject.toml").write_text("[project]\nname='shop'\ndependencies=['fastapi','redis']\n")
    b = tmp_path / "blog"
    b.mkdir()
    (b / "README.md").write_text("A blog\n")
    home = tmp_path / "home"
    ws = Workspace(home / "workspace.json")
    creds = Credentials(env={}, home=tmp_path / "userhome")
    app = create_app(
        workspace=ws,
        credentials=creds,
        github=FakeGitHub(),
        home=home,
        user_skills_dir=tmp_path / "none",
        web_dist=tmp_path / "nodist",
        host_login=lambda: {"email": "me@example.com", "plan": "max", "method": "claude.ai"},
        cli_model=FakeCli,
    )
    return TestClient(app, base_url=BASE), a, b, home


def test_no_repo_means_attach_first(env):
    c, *_ = env
    assert c.get("/api/repos").json() == []
    r = c.get("/api/project")
    assert r.status_code == 409 and r.json()["detail"] == "Attach a repo first."


def test_repo_outside_home_gets_a_warning(env):
    c, a, *_ = env
    if a.resolve().is_relative_to(Path.home().resolve()):
        pytest.skip("the test folder is under the home folder on this machine")
    r = c.post("/api/repos", json={"path": str(a)}, headers=ORIGIN).json()
    assert "outside your home folder" in r["warning"] and "pg doctor" in r["warning"]


def test_repo_under_home_has_no_warning(env):
    c, *_ = env
    base = Path.home() / ".cache" / "pg-t5a-test"
    folder = base / "shop"
    (folder / "src").mkdir(parents=True)
    (folder / "README.md").write_text("A shop\n")
    try:
        r = c.post("/api/repos", json={"path": str(folder)}, headers=ORIGIN)
        assert r.status_code == 200 and "warning" not in r.json()
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_attach_several_repos_and_switch(env):
    c, a, b, home = env
    ra = c.post("/api/repos", json={"path": str(a)}, headers=ORIGIN).json()
    rb = c.post("/api/repos", json={"path": str(b)}, headers=ORIGIN).json()
    assert [r["name"] for r in c.get("/api/repos").json()] == ["shop", "blog"]
    assert c.get("/api/project").json()["name"] == "shop"  # the first by default
    assert c.get(f"/api/project?repo={rb['id']}").json()["name"] == "blog"
    assert c.get(f"/api/project?repo={ra['id']}").json()["scanned"] is True  # read on attach
    saved = json.loads((home / "workspace.json").read_text())
    assert len(saved["repos"]) == 2
    bad = c.post("/api/repos", json={"path": str(a / "missing")}, headers=ORIGIN)
    assert bad.status_code == 422 and "not a folder" in bad.json()["detail"]
    c.delete(f"/api/repos/{rb['id']}", headers=ORIGIN)
    assert [r["name"] for r in c.get("/api/repos").json()] == ["shop"]
    assert c.get("/api/project?repo=nope").status_code == 404


def test_architecture_of_the_repo(env):
    c, a, *_ = env
    c.post("/api/repos", json={"path": str(a)}, headers=ORIGIN)
    arch = c.get("/api/architecture").json()
    ids = {x["id"] for x in arch["components"]}
    assert {"shop.api", "shop.db", "redis"} <= ids
    assert ("shop.api", "shop.db") in {(x["from"], x["to"]) for x in arch["connections"]}


def test_agents_and_typed_keys_never_come_back(env):
    c, *_ = env
    agents = {x["id"]: x for x in c.get("/api/agents").json()}
    assert set(agents) == {"claude-code", "codex", "opencode", "gemini-cli"}
    assert agents["claude-code"]["ready"] is False
    # Only Claude Code stops itself mid-trial at a dollar cap (trial-budget: in_trial_cap).
    assert {a: x["budget_cap"] for a, x in agents.items()} == {
        "claude-code": True,
        "codex": False,
        "opencode": False,
        "gemini-cli": False,
    }
    r = c.put(
        "/api/credentials",
        json={"agent": "claude-code", "option": "api-key", "value": "sk-secret"},
        headers=ORIGIN,
    )
    assert r.json() == {"agent": "claude-code", "ready": True}
    assert "sk-secret" not in c.get("/api/agents").text
    bad = c.put(
        "/api/credentials", json={"agent": "codex", "option": "login", "value": "x"}, headers=ORIGIN
    )
    assert bad.status_code == 422
    c.delete("/api/credentials/claude-code", headers=ORIGIN)
    assert {x["id"]: x for x in c.get("/api/agents").json()}["claude-code"]["ready"] is False


def test_write_your_own_scenario(env):
    c, a, *_ = env
    c.post("/api/repos", json={"path": str(a)}, headers=ORIGIN)
    body = {
        "id": "refund-cap",
        "title": "Refund cap",
        "instruction": "Cap refunds at $100.",
        "check": "pytest -q",
    }
    s = c.post("/api/scenarios", json=body, headers=ORIGIN).json()
    assert s["origin"] == "user" and s["runnable"] is True
    assert c.post("/api/scenarios", json=body, headers=ORIGIN).status_code == 409
    assert c.post("/api/scenarios", json=body | {"id": "Bad Id"}, headers=ORIGIN).status_code == 422


def test_catalog_builds_in_the_background_then_ranks(env):
    c, a, *_ = env
    c.post("/api/repos", json={"path": str(a)}, headers=ORIGIN)
    import time

    first = c.get("/api/catalog?category=skill").json()
    for _ in range(50):
        if not first["loading"] and first["items"]:
            break
        time.sleep(0.05)
        first = c.get("/api/catalog?category=skill").json()
    # Recommended: what fits this repo (FastAPI) before the famous one that doesn't.
    assert [i["id"] for i in first["items"]][:2] == ["tiny/fastapi-helper", "anthropics/skills"]
    assert set(first["counts"]) == {"skill", "agent", "mcp", "hook", "harness", "workflow", "eval"}
    assert first["counts"]["skill"] == len(first["items"])
    rel = c.get("/api/catalog?category=skill&view=relevant").json()
    assert rel["items"][0]["id"] == "tiny/fastapi-helper"  # matches this repo's FastAPI
    assert "fastapi" in rel["terms"]
    assert c.get("/api/catalog?category=nope").status_code == 422


def test_install_a_skill_and_see_it_in_the_library(env):
    c, a, _, home = env
    c.post("/api/repos", json={"path": str(a)}, headers=ORIGIN)
    skills = c.get("/api/catalog/skills?name=acme/test-first").json()
    assert [s["name"] for s in skills] == ["review", "tdd"]
    r = c.post(
        "/api/catalog/install",
        json={"repo": "acme/test-first", "path": "skills/tdd"},
        headers=ORIGIN,
    ).json()
    assert Path(r["path"]).parent == home / "library"
    lib = c.get("/api/treatments").json()["installed"]
    assert [(x["name"], x["source"]) for x in lib] == [("tdd", "acme/test-first")]


def test_estimate_uses_the_mac_login_or_a_rough_guess(env):
    c, a, _, home = env
    c.post("/api/repos", json={"path": str(a)}, headers=ORIGIN)
    r = c.post(
        "/api/catalog/install",
        json={"repo": "acme/test-first", "path": "skills/tdd"},
        headers=ORIGIN,
    ).json()
    # By default no model is asked, signed in or not: the rough guess, and what sharpening costs.
    plain = c.post(
        "/api/estimate", json={"treatment_path": r["path"], "steps": ["fix"]}, headers=ORIGIN
    ).json()
    assert plain["basis"] == "rough" and plain["sharpen_usd"] == 0.01
    est = c.post(
        "/api/estimate",
        json={"treatment_path": r["path"], "steps": ["fix"], "model": True},
        headers=ORIGIN,
    ).json()
    # Asked for: signed in on this Mac, the model goes through the claude CLI (faked here).
    assert est["basis"] == "estimate" and est["likely"] == 3
    quick = c.post(
        "/api/estimate",
        json={"treatment_path": r["path"], "steps": ["fix"], "quick": True},
        headers=ORIGIN,
    ).json()
    assert quick["basis"] == "rough"


def test_adding_the_same_folder_by_another_path_returns_the_attached_repo(env):
    c, a, _, home = env
    first = c.post("/api/repos", json={"path": str(a)}, headers=ORIGIN).json()
    again = c.post("/api/repos", json={"path": f"{a}/src/.."}, headers=ORIGIN).json()
    assert again["id"] == first["id"]
    assert [r["id"] for r in c.get("/api/repos").json()] == [first["id"]]


def test_estimate_batch_is_rough_only_in_order_and_bounded(env):
    c, a, _, home = env
    c.post("/api/repos", json={"path": str(a)}, headers=ORIGIN)
    r = c.post(
        "/api/catalog/install",
        json={"repo": "acme/test-first", "path": "skills/tdd"},
        headers=ORIGIN,
    ).json()
    from proving_ground.api import app as app_mod

    got = c.post(
        "/api/estimate/batch",
        json={
            "items": [
                {"treatment_path": r["path"], "steps": ["fix"]},
                {"treatment_path": str(a / "no-such-skill")},
                {"treatment_path": r["path"]},
            ]
        },
        headers=ORIGIN,
    )
    assert got.status_code == 200
    es = got.json()["estimates"]
    assert [e["basis"] for e in es] == ["rough", "none", "rough"]
    assert "no SKILL.md" in es[1]["reason"]
    assert es[0]["sharpen_usd"] == 0.01  # what sharpening one would cost, on its own click
    # The same as asking one at a time, without a model.
    one = c.post(
        "/api/estimate", json={"treatment_path": r["path"], "steps": ["fix"]}, headers=ORIGIN
    ).json()
    assert es[0]["likely"] == one["likely"] and es[0]["reason"] == one["reason"]
    # Bounded: a request over the rough-estimate skill's batch_max is refused.
    big = c.post(
        "/api/estimate/batch",
        json={"items": [{"treatment_path": r["path"]}] * (app_mod.ESTIMATE_BATCH_MAX + 1)},
        headers=ORIGIN,
    )
    assert big.status_code == 422


def test_runs_need_the_chosen_agent_signed_in(env):
    c, a, *_ = env
    c.post("/api/repos", json={"path": str(a)}, headers=ORIGIN)
    r = c.post(
        "/api/experiments",
        json={"treatment_path": str(a), "budget": 1, "agent": "codex"},
        headers=ORIGIN,
    )
    assert r.status_code == 400 and "Sign in to Codex" in r.json()["detail"]


def test_map_with_archify_runs_in_the_background(tmp_path):
    import subprocess
    import time

    from test_architecture_map import SPEC

    from proving_ground.architecture.mapper import map_architecture

    repo = tmp_path / "shop"
    repo.mkdir()
    calls = []

    def mapper(root, agent, env):
        calls.append((root, agent, env))
        out = json.dumps(SPEC)
        return map_architecture(
            root, agent, env, run=lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, out, "")
        )

    creds = Credentials(env={"CLAUDE_CODE_OAUTH_TOKEN": "tok"}, home=tmp_path / "userhome")
    app = create_app(
        root=repo,
        credentials=creds,
        github=FakeGitHub(),
        home=tmp_path / "home",
        user_skills_dir=tmp_path / "none",
        web_dist=tmp_path / "nodist",
        mapper=mapper,
        host_login=lambda: None,
    )
    c = TestClient(app, base_url=BASE)
    assert c.get("/api/architecture/map").json() == {"state": "idle"}
    assert (
        c.post("/api/architecture/map", json={"agent": "codex"}, headers=ORIGIN).status_code == 400
    )
    r = c.post("/api/architecture/map", json={"agent": "claude-code"}, headers=ORIGIN)
    assert r.status_code == 202 and r.json()["state"] == "running"
    for _ in range(100):
        if c.get("/api/architecture/map").json()["state"] != "running":
            break
        time.sleep(0.02)
    assert c.get("/api/architecture/map").json()["state"] == "done"
    # The secret only; no sandbox flags for a CLI on this machine.
    assert calls[0][2] == {"CLAUDE_CODE_OAUTH_TOKEN": "tok"}
    a = c.get("/api/architecture").json()
    assert a["source"] == "mapped" and [x["id"] for x in a["components"]] == ["web", "api", "db"]


def test_agents_show_the_login_on_this_machine_and_sign_in_through_the_cli(env):
    c, *_ = env
    agents = {a["id"]: a for a in c.get("/api/agents").json()}
    assert agents["claude-code"]["host"] == {
        "email": "me@example.com",
        "plan": "max",
        "method": "claude.ai",
    }
    # Signed in on this Mac is not the same as ready for sandboxed runs.
    assert agents["claude-code"]["ready"] is False
    assert agents["claude-code"]["login"]["auto"] is True
    assert agents["gemini-cli"]["login"]["auto"] is False and agents["codex"]["host"] is None
    assert c.get("/api/agents/codex/login").json()["state"] == "idle"
    assert c.get("/api/agents/nope/login").status_code == 404


def test_readme_and_skill_text_for_the_details_panel(env):
    c, a, _, _ = env
    c.post("/api/repos", json={"path": str(a)}, headers=ORIGIN)
    assert c.get("/api/catalog/readme", params={"name": "../../etc"}).status_code == 422
    r = c.post(
        "/api/catalog/install",
        json={"repo": "acme/test-first", "path": "skills/tdd"},
        headers=ORIGIN,
    ).json()
    s = c.get("/api/skill", params={"path": r["path"]}).json()
    assert "Write the test." in s["text"] and "SKILL.md" in s["files"]
    # Nothing outside the known skill folders.
    assert c.get("/api/skill", params={"path": "/etc"}).status_code == 404
