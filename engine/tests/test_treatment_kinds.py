import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from proving_ground import adherence, skills
from proving_ground.api.views import treatments_json
from proving_ground.files import save_scenario
from proving_ground.models import Scenario, TreatmentKind, detect_kind, treatment_from_path
from proving_ground.sandbox.treatments import merge_settings, unpinned_installs
from proving_ground.service import ServiceError, execute, prepare_experiment
from proving_ground.store import Store

HOOKS = {"PostToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "echo hi"}]}]}
MCP = {"mcpServers": {"docs": {"command": "npx", "args": ["-y", "docs-mcp@1.2.3"]}}}


def make(tmp_path: Path, kind: str) -> Path:
    d = tmp_path / "lib" / f"my-{kind}"
    d.mkdir(parents=True)
    if kind == "hook":
        (d / "hooks.json").write_text(json.dumps(HOOKS))
    elif kind == "mcp":
        (d / "mcp.json").write_text(json.dumps(MCP))
        (d / "install.sh").write_text("#!/bin/bash\nnpm install -g docs-mcp@1.2.3\n")
    else:
        (d / "CLAUDE.md").write_text("Always write tests.\n")
    return d


def fake_result(reward=1.0):
    return SimpleNamespace(
        exception_info=None,
        verifier_result=SimpleNamespace(rewards={"reward": reward}),
        agent_result=SimpleNamespace(n_input_tokens=1, n_output_tokens=1, cost_usd=0.1),
        started_at=None,
        finished_at=None,
        trial_name="t",
    )


@pytest.fixture
def project(tmp_path: Path, monkeypatch):
    seen = []

    def fake(req):
        seen.append(req)
        return fake_result(0.0 if req.agent == "nop" else 1.0)

    monkeypatch.setattr("proving_ground.runner.harbor.harbor_executor", fake)
    root = tmp_path / "proj"
    (root / ".claude").mkdir(parents=True)
    (root / "app.py").write_text("x")
    (root / "CLAUDE.md").write_text("repo's own rules\n")
    (root / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Bash(ls)"]},
                "hooks": {"PostToolUse": [{"hooks": [{"type": "command", "command": "own"}]}]},
            }
        )
    )
    save_scenario(root, Scenario(id="a", instruction="Fix.", check="true", check_status="approved"))
    return root, seen


def repo_of(root: Path, arm_dir: str, sid="a") -> Path:
    return root / ".proving-ground" / "runs" / "1" / arm_dir / sid / "environment" / "repo"


def test_detection(tmp_path: Path):
    assert detect_kind(make(tmp_path, "hook")) is TreatmentKind.HOOK
    assert detect_kind(make(tmp_path, "mcp")) is TreatmentKind.MCP
    folder = make(tmp_path, "instructions")
    assert detect_kind(folder) is TreatmentKind.INSTRUCTIONS
    assert detect_kind(folder / "CLAUDE.md") is TreatmentKind.INSTRUCTIONS
    assert treatment_from_path(folder / "CLAUDE.md").kind is TreatmentKind.INSTRUCTIONS
    sk = tmp_path / "sk"
    sk.mkdir()
    (sk / "SKILL.md").write_text("x")
    assert detect_kind(sk) is TreatmentKind.SKILL
    (sk / "hooks.json").write_text("{}")
    with pytest.raises(ValueError, match="more than one"):
        detect_kind(sk)
    other = tmp_path / "notes.md"
    other.write_text("x")
    with pytest.raises(ValueError, match="CLAUDE.md or AGENTS.md"):
        detect_kind(other)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="hooks.json"):
        detect_kind(empty)


def test_skill_flow_unchanged(project):
    root, seen = project
    sk = root.parent / "sk"
    sk.mkdir()
    (sk / "SKILL.md").write_text("---\nname: sk\n---\nx\n")
    p = prepare_experiment(root, sk, budget=10, n=2)
    assert not (root / ".proving-ground" / "runs" / "1" / "tasks-with").exists()
    assert p.runner._with_tasks is None
    execute(p, lambda e: None)
    with_reqs = [r for r in seen if r.skills]
    assert with_reqs and all(r.task_dir.parent.name == "tasks" for r in seen)
    assert (repo_of(root, "tasks") / "CLAUDE.md").read_text() == "repo's own rules\n"


def test_hook_arms(project):
    root, seen = project
    p = prepare_experiment(root, make(root.parent, "hook"), budget=10, n=2)
    execute(p, lambda e: None)
    without = json.loads((repo_of(root, "tasks") / ".claude" / "settings.json").read_text())
    assert without["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "own"
    assert len(without["hooks"]["PostToolUse"]) == 1
    with_ = json.loads((repo_of(root, "tasks-with") / ".claude" / "settings.json").read_text())
    cmds = [g["hooks"][0]["command"] for g in with_["hooks"]["PostToolUse"]]
    assert cmds == ["own", "echo hi"]  # merged, repo's own first
    assert with_["permissions"] == {"allow": ["Bash(ls)"]}  # the rest of settings preserved
    # each arm ran its own task folder; no skill was handed over
    dirs = {r.task_dir.parent.name for r in seen}
    assert dirs == {"tasks", "tasks-with"} and all(not r.skills for r in seen)


def test_mcp_arms_share_install(project):
    root, _ = project
    prepare_experiment(root, make(root.parent, "mcp"), budget=10, n=2)
    assert not (repo_of(root, "tasks") / ".mcp.json").exists()
    cfg = json.loads((repo_of(root, "tasks-with") / ".mcp.json").read_text())
    assert cfg == MCP
    st = json.loads((repo_of(root, "tasks-with") / ".claude" / "settings.json").read_text())
    assert st["enabledMcpjsonServers"] == ["docs"]
    assert "mcp" not in json.dumps(
        json.loads((repo_of(root, "tasks") / ".claude" / "settings.json").read_text())
    ).lower().replace("enabledmcp", "")
    for arm in ("tasks", "tasks-with"):
        task = root / ".proving-ground" / "runs" / "1" / arm / "a" / "environment"
        assert "npm install -g docs-mcp@1.2.3" in (task / "pg" / "mcp-install.sh").read_text()
        assert "RUN bash /pg/mcp-install.sh" in (task / "Dockerfile").read_text()
    meta = json.loads((root / ".proving-ground" / "runs" / "1" / "meta.json").read_text())
    assert meta["mcp_servers"] == ["docs"]


def test_mcp_merges_existing_config_and_rejects_unpinned(project):
    root, _ = project
    (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"own": {"command": "x"}}}))
    prepare_experiment(root, make(root.parent, "mcp"), budget=10, n=2)
    cfg = json.loads((repo_of(root, "tasks-with") / ".mcp.json").read_text())
    assert set(cfg["mcpServers"]) == {"own", "docs"}


def test_unpinned_install_rejected(project):
    root, _ = project
    d = make(root.parent, "mcp")
    (d / "install.sh").write_text("npm install -g docs-mcp\n")
    with pytest.raises(ServiceError, match="pin exact versions"):
        prepare_experiment(root, d, budget=10, n=2)
    assert unpinned_installs("pip install foo==1.0\nnpx -y bar@latest\nnpm i baz@2.0.1") == [
        "npx -y bar@latest"
    ]


def test_instructions_arms(project):
    root, seen = project
    p = prepare_experiment(root, make(root.parent, "instructions"), budget=10, n=2)
    assert (repo_of(root, "tasks") / "CLAUDE.md").read_text() == "repo's own rules\n"
    assert (repo_of(root, "tasks-with") / "CLAUDE.md").read_text() == "Always write tests.\n"
    execute(p, lambda e: None)
    assert {r.task_dir.parent.name for r in seen} == {"tasks", "tasks-with"}


def test_agents_md_file_replaces_agents_md(project):
    root, _ = project
    (root / "AGENTS.md").write_text("old")
    f = root.parent / "AGENTS.md"
    f.write_text("new")
    prepare_experiment(root, f, budget=10, n=2)
    assert (repo_of(root, "tasks-with") / "AGENTS.md").read_text() == "new"
    assert (repo_of(root, "tasks-with") / "CLAUDE.md").read_text() == "repo's own rules\n"
    assert (repo_of(root, "tasks") / "AGENTS.md").read_text() == "old"


def test_merge_settings_without_existing():
    out = merge_settings({}, HOOKS)
    assert out == {"hooks": HOOKS}


def test_mcp_adherence_counts(tmp_path: Path):
    trial = tmp_path / "t1"
    sess = trial / "agent" / "sessions"
    sess.mkdir(parents=True)

    def ev(*names):
        return json.dumps(
            {"message": {"content": [{"type": "tool_use", "name": n, "input": {}} for n in names]}}
        )

    (sess / "s.jsonl").write_text(
        "\n".join(
            [ev("Read", "mcp__docs__search"), "not json", ev("mcp__docs__fetch", "mcp__other__x")]
        )
    )
    assert adherence.mcp_tool_calls(trial, ["docs"]) == {"docs": 2}
    assert adherence.mcp_tool_calls(tmp_path / "none", ["docs"]) is None
    s = adherence.summarize_mcp([{"docs": 2}, {"docs": 0}, None])
    assert s["used"] == 1 and s["read"] == 2 and s["trials"] == 3
    assert s["text"] == "used the MCP server in 1 of 2 trials"


def test_listing_by_kind(tmp_path: Path):
    root = tmp_path / "proj"
    (root / ".claude" / "hooks").mkdir(parents=True)
    (root / ".claude" / "hooks" / "fmt").mkdir()
    (root / ".claude" / "hooks" / "fmt" / "hooks.json").write_text(json.dumps(HOOKS))
    (root / "AGENTS.md").write_text("x")
    (root / ".claude" / "skills" / "s").mkdir(parents=True)
    (root / ".claude" / "skills" / "s" / "SKILL.md").write_text("x")
    user = tmp_path / "user"
    (user / "m").mkdir(parents=True)
    (user / "m" / "mcp.json").write_text(json.dumps(MCP))
    store = Store.for_project(root)
    out = treatments_json(root, store, [], [], user)
    got = {(c["name"], c["kind"], c["source"]) for c in out["configs"]}
    assert got == {
        ("fmt", "hook", "repo"),
        ("AGENTS.md", "instructions", "repo"),
        ("m", "mcp", "user"),
    }


def test_skill_registered():
    assert skills.value("treatment-kinds", "hooks_file") == "hooks.json"
