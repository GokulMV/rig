"""Hooks, MCP servers and instructions as the change, through the API: listed with what each arm
gets, started from Measure's request, and written into the "with" arm's workspace only."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from proving_ground.api.app import create_app
from proving_ground.files import save_scenario
from proving_ground.models import Scenario

BASE = "http://127.0.0.1:7357"
ORIGIN = {"origin": BASE}
HOOKS = {"PostToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "ruff ."}]}]}
MCP = {"mcpServers": {"docs": {"command": "npx", "args": ["-y", "docs-mcp@1.2.3"]}}}


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    seen = []

    def fake(req):
        seen.append(req)
        return SimpleNamespace(
            exception_info=None,
            verifier_result=SimpleNamespace(rewards={"reward": 0.0 if req.agent == "nop" else 1.0}),
            agent_result=SimpleNamespace(n_input_tokens=10, n_output_tokens=5, cost_usd=0.1),
            started_at=None,
            finished_at=None,
            trial_name="t",
        )

    monkeypatch.setattr("proving_ground.runner.harbor.harbor_executor", fake)
    root = tmp_path / "proj"
    (root / ".claude" / "hooks" / "lint").mkdir(parents=True)
    (root / ".claude" / "hooks" / "lint" / "hooks.json").write_text(json.dumps(HOOKS))
    (root / "app.py").write_text("x")
    (root / "CLAUDE.md").write_text("Run the tests.\n")
    save_scenario(root, Scenario(id="a", instruction="Fix.", check="true", check_status="approved"))
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "seed")
    user = tmp_path / "user"
    (user / "docs").mkdir(parents=True)
    (user / "docs" / "mcp.json").write_text(json.dumps(MCP))
    return root, user, seen


def client(root: Path, user: Path) -> TestClient:
    return TestClient(create_app(root, user_skills_dir=user), base_url=BASE)


def configs(c: TestClient) -> dict[str, dict]:
    return {x["name"]: x for x in c.get("/api/treatments").json()["configs"]}


def start(c: TestClient, path: str) -> dict:
    r = c.post(
        "/api/experiments", json={"treatment_path": path, "n": 1, "budget": 10}, headers=ORIGIN
    )
    assert r.status_code == 200, r.text
    with c.stream("GET", f"/api/experiments/{r.json()['id']}/events") as s:
        for _ in s.iter_lines():
            pass
    return r.json()


def repo_of(root: Path, eid: int, arm_dir: str) -> Path:
    return root / ".proving-ground" / "runs" / str(eid) / arm_dir / "a" / "environment" / "repo"


def test_the_listing_says_what_each_arm_gets(env):
    root, user, _ = env
    got = configs(client(root, user))
    assert got["lint"]["kind"] == "hook" and got["lint"]["compare"] == "hook"
    assert got["lint"]["compare_text"].startswith("With: its hooks are merged")
    assert got["docs"]["kind"] == "mcp" and got["docs"]["source"] == "user"
    md = got["CLAUDE.md"]
    assert md["kind"] == "instructions" and md["compare"] == "same"
    assert md["text"] == "Run the tests.\n" and md["file"] == "CLAUDE.md"
    assert "both arms already have" in md["compare_text"]


def test_the_committed_claude_md_is_refused_it_would_measure_nothing(env):
    root, user, _ = env
    c = client(root, user)
    r = c.post(
        "/api/experiments",
        json={"treatment_path": str(root / "CLAUDE.md"), "n": 1, "budget": 10},
        headers=ORIGIN,
    )
    assert r.status_code == 422
    assert "Both arms would get the same CLAUDE.md" in r.json()["detail"]


def test_an_uncommitted_edit_is_measured_against_the_committed_file(env):
    root, user, seen = env
    (root / "CLAUDE.md").write_text("Run the tests. Say less.\n")
    c = client(root, user)
    assert configs(c)["CLAUDE.md"]["compare"] == "edited"
    eid = start(c, str(root / "CLAUDE.md"))["id"]
    assert (repo_of(root, eid, "tasks-with") / "CLAUDE.md").read_text() == (
        "Run the tests. Say less.\n"
    )
    assert (repo_of(root, eid, "tasks") / "CLAUDE.md").read_text() == "Run the tests.\n"
    assert {r.task_dir.parent.name for r in seen if r.agent != "nop"} == {"tasks", "tasks-with"}
    rig = c.get(f"/api/experiments/{eid}").json()["rig"]
    fol = next(p for p in rig["parts"] if p["id"] == "followed")
    assert fol["score"] is None and "always loaded" in fol["detail"]


def test_an_edited_copy_saved_from_measure_replaces_claude_md_in_the_with_arm_only(env):
    root, user, _ = env
    c = client(root, user)
    r = c.post(
        "/api/treatments/instructions",
        json={"text": "Run the tests. Answer in one line."},
        headers=ORIGIN,
    )
    assert r.status_code == 200, r.text
    draft = configs(c)["claude-md-edit"]
    assert draft["source"] == "draft" and draft["compare"] == "replaces"
    assert draft["text"] == "Run the tests. Answer in one line.\n"
    eid = start(c, draft["path"])["id"]
    assert (repo_of(root, eid, "tasks-with") / "CLAUDE.md").read_text() == (
        "Run the tests. Answer in one line.\n"
    )
    assert (repo_of(root, eid, "tasks") / "CLAUDE.md").read_text() == "Run the tests.\n"
    for arm in ("tasks", "tasks-with"):  # the draft itself is in neither repo copy
        assert not (repo_of(root, eid, arm) / ".proving-ground").exists()
    # Saved again: the same draft, its new text.
    c.post("/api/treatments/instructions", json={"text": "v2"}, headers=ORIGIN)
    assert configs(c)["claude-md-edit"]["text"] == "v2\n"
    bad = c.post("/api/treatments/instructions", json={"text": "  "}, headers=ORIGIN)
    assert bad.status_code == 422


def test_a_new_agents_md_is_measured_against_none(env):
    root, user, _ = env
    (root / "AGENTS.md").write_text("Be brief.\n")
    c = client(root, user)
    md = configs(c)["AGENTS.md"]
    assert md["compare"] == "new" and "Without: none" in md["compare_text"]
    eid = start(c, md["path"])["id"]
    assert (repo_of(root, eid, "tasks-with") / "AGENTS.md").read_text() == "Be brief.\n"
    assert not (repo_of(root, eid, "tasks") / "AGENTS.md").exists()


def test_a_hook_from_the_repo_is_merged_into_the_with_arm(env):
    root, user, _ = env
    c = client(root, user)
    eid = start(c, configs(c)["lint"]["path"])["id"]
    st = json.loads((repo_of(root, eid, "tasks-with") / ".claude" / "settings.json").read_text())
    assert st["hooks"] == HOOKS
    assert not (repo_of(root, eid, "tasks") / ".claude" / "settings.json").exists()
    got = c.get(f"/api/experiments/{eid}").json()
    assert got["treatment_kind"] == "hook"
    fol = next(p for p in got["rig"]["parts"] if p["id"] == "followed")
    assert fol["detail"].startswith("a hook runs by itself")


def test_an_mcp_server_from_the_user_folder_is_configured_and_approved(env):
    root, user, _ = env
    c = client(root, user)
    eid = start(c, configs(c)["docs"]["path"])["id"]
    assert json.loads((repo_of(root, eid, "tasks-with") / ".mcp.json").read_text()) == MCP
    st = json.loads((repo_of(root, eid, "tasks-with") / ".claude" / "settings.json").read_text())
    assert st["enabledMcpjsonServers"] == ["docs"]
    assert not (repo_of(root, eid, "tasks") / ".mcp.json").exists()


def test_outside_git_the_root_file_is_the_same_both_ways(tmp_path: Path):
    from proving_ground.sandbox.treatments import instruction_compare

    root = tmp_path / "plain"
    root.mkdir()
    (root / "CLAUDE.md").write_text("x")
    assert instruction_compare(root, root / "CLAUDE.md") == "same"
    other = tmp_path / "lib" / "terse"
    other.mkdir(parents=True)
    (other / "CLAUDE.md").write_text("y")
    assert instruction_compare(root, other) == "replaces"
    (root / "CLAUDE.md").unlink()
    assert instruction_compare(root, other) == "adds"
