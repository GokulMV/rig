"""Stale-baseline protection, the reuse toggle and the nudge toggle (fakes only)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_bench import _lab_client, _starter, _wait

from proving_ground.baseline import env_fingerprint
from proving_ground.runner.harbor import HarborRunner


def test_fingerprint_changes_with_recipe_and_server(tmp_path: Path):
    base = env_fingerprint(tmp_path, "claude-code", "m")
    assert base == env_fingerprint(tmp_path, "claude-code", "m")
    (tmp_path / ".proving-ground").mkdir()
    (tmp_path / ".proving-ground" / "Dockerfile.base").write_text("FROM scratch\n")
    assert env_fingerprint(tmp_path, "claude-code", "m") != base
    a = env_fingerprint(tmp_path, "claude-code", "m", {"ANTHROPIC_BASE_URL": "http://h:1"})
    b = env_fingerprint(tmp_path, "claude-code", "m2", {"ANTHROPIC_BASE_URL": "http://h:1"})
    assert a != b and a != env_fingerprint(tmp_path, "claude-code", "m")


def _run_twice(tmp_path, monkeypatch, second: dict, between=None):
    from test_api_workspace import ORIGIN

    c, calls = _lab_client(tmp_path, monkeypatch, lambda req: 1.0 if req.skills else 0.0)
    a, b = _starter(c, "Fix a bug"), _starter(c, "Refactor safely")
    body = {"bench": "qa", "budget": 5, "auto": False}
    assert c.post("/api/lab/run", json=body | {"workflow": a}, headers=ORIGIN).status_code == 200
    _wait(c, 1)
    if between:
        between(tmp_path)
    before = len([q for q in calls if q.agent != "nop" and not q.skills])
    assert (
        c.post("/api/lab/run", json=body | second | {"workflow": b}, headers=ORIGIN).status_code
        == 200
    )
    _wait(c, 2)
    return len([q for q in calls if q.agent != "nop" and not q.skills]) - before


def test_matching_fingerprint_allows_reuse(tmp_path: Path, monkeypatch):
    assert _run_twice(tmp_path, monkeypatch, {}) == 0


def test_reuse_off_runs_the_baseline_fresh(tmp_path: Path, monkeypatch):
    assert _run_twice(tmp_path, monkeypatch, {"reuse_baseline": False}) > 0


def test_a_changed_fingerprint_or_a_missing_one_blocks_reuse(tmp_path: Path, monkeypatch):
    import json

    def corrupt(tmp: Path, drop: bool):
        for f in (tmp / "home" / "benches").glob("*/.proving-ground/runs/*/meta.json"):
            m = json.loads(f.read_text())
            if drop:
                m.pop("env_fingerprint")
            else:
                m["env_fingerprint"] = "stale"
            f.write_text(json.dumps(m))

    assert _run_twice(tmp_path / "a", monkeypatch, {}, lambda t: corrupt(t, False)) > 0
    assert _run_twice(tmp_path / "b", monkeypatch, {}, lambda t: corrupt(t, True)) > 0


@pytest.mark.parametrize("nudge", [None, True, False])
@pytest.mark.parametrize("workflow", [True, False])
def test_nudge_decides_whether_the_prompt_names_the_treatment(
    tmp_path: Path, nudge, workflow: bool
):
    skill = tmp_path / "tdd"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: tdd\ndescription: d\n---\nbody\n")
    if workflow:
        (skill / "workflow.json").write_text("{}")
    r = HarborRunner({}, tmp_path / "trials", "anthropic/x", nudge=nudge)
    handed = r._handed(skill)
    expected = workflow if nudge is None else nudge
    assert (handed is not None) == expected
    if handed:
        assert "`tdd`" in handed.read_text()
