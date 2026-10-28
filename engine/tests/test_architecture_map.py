import json
import subprocess

import pytest

from proving_ground.architecture import load_architecture
from proving_ground.architecture.mapper import MapError, extract_spec, map_architecture

SPEC = {
    "diagram_type": "architecture",
    "meta": {"title": "shop architecture"},
    "components": [
        {"id": "web", "type": "frontend", "label": "Web"},
        {"id": "api", "type": "backend", "label": "API", "sublabel": "FastAPI"},
        {"id": "db", "type": "database", "label": "Postgres"},
    ],
    "connections": [
        {"from": "web", "to": "api", "label": "HTTPS"},
        {"from": "api", "to": "db", "label": "SQL"},
        {"from": "api", "to": "ghost"},
    ],
}


def fake_run(stdout, code=0, seen=None):
    def run(cmd, **kw):
        if seen is not None:
            seen.update(cmd=cmd, **kw)
        return subprocess.CompletedProcess(cmd, code, stdout=stdout, stderr="boom")

    return run


def test_extract_from_claude_json_wrapper_and_fences():
    wrapped = json.dumps(
        {"type": "result", "result": "Here:\n```json\n" + json.dumps(SPEC) + "\n```"}
    )
    assert extract_spec(wrapped)["meta"]["title"] == "shop architecture"
    assert (
        extract_spec("prose {" + json.dumps(SPEC)[1:] + " more")["diagram_type"] == "architecture"
    )
    with pytest.raises(MapError):
        extract_spec("no json here")
    with pytest.raises(MapError, match="stopped"):
        extract_spec(json.dumps({"result": "rate limited", "is_error": True}))


def test_map_runs_read_only_and_keeps_the_spec(tmp_path):
    seen: dict = {}
    a = map_architecture(
        tmp_path, "claude-code", {"X": "1"}, run=fake_run(json.dumps(SPEC), seen=seen)
    )
    cmd = seen["cmd"]
    assert cmd[0] == "claude" and "-p" in cmd
    assert cmd[cmd.index("--tools") + 1] == "Read,Glob,Grep"
    assert "--strict-mcp-config" in cmd
    assert seen["cwd"] == tmp_path
    assert seen["env"]["ARCHIFY_UPDATE_CHECK_DISABLED"] == "1" and seen["env"]["X"] == "1"

    assert a.source == "mapped"
    assert [c.id for c in a.components] == ["web", "api", "db"]
    # The line to a component that isn't there is dropped.
    assert [(c.from_, c.to) for c in a.connections] == [("web", "api"), ("api", "db")]
    # Kept: a fresh load (cache refreshed) still reads the mapped spec.
    assert load_architecture(tmp_path, refresh=True).source == "mapped"


def test_repo_spec_wins_over_mapped(tmp_path):
    map_architecture(tmp_path, "claude-code", run=fake_run(json.dumps(SPEC)))
    own = dict(SPEC, meta={"title": "own"})
    (tmp_path / "shop.architecture.json").write_text(json.dumps(own))
    a = load_architecture(tmp_path, refresh=True)
    assert (a.source, a.title) == ("archify", "own")


def test_map_refuses_bad_output_and_other_agents(tmp_path):
    with pytest.raises(MapError, match="Claude Code"):
        map_architecture(tmp_path, "codex", run=fake_run("{}"))
    with pytest.raises(MapError, match="not an architecture"):
        map_architecture(tmp_path, "claude-code", run=fake_run(json.dumps({"x": 1})))
    with pytest.raises(MapError, match="no components"):
        map_architecture(
            tmp_path, "claude-code", run=fake_run(json.dumps(dict(SPEC, components=[])))
        )
    with pytest.raises(MapError, match="failed"):
        map_architecture(tmp_path, "claude-code", run=fake_run("", code=1))
    assert not (tmp_path / ".proving-ground" / "archify.json").exists()
