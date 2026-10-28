import subprocess
import tomllib
from pathlib import Path

import pytest

from proving_ground.models import Scenario
from proving_ground.sandbox.compiler import (
    DEFAULT_BASE_DOCKERFILE,
    UnsupportedFaultError,
    compile_task,
)


def snap(tmp_path: Path) -> Path:
    s = tmp_path / "snap"
    s.mkdir(exist_ok=True)
    (s / "app.py").write_text("x")
    return s


def sc(**kw) -> Scenario:
    data = {"id": "fix-it", "instruction": "Fix the bug.", "check": "python3 -m pytest -q"}
    data.update(kw)
    return Scenario.model_validate(data)


def test_layout_and_files(tmp_path: Path):
    out = compile_task(sc(timeout=900), tmp_path, snap(tmp_path), tmp_path / "task")
    assert (out / "instruction.md").read_text() == "Fix the bug.\n"
    assert (out / "environment" / "repo" / "app.py").read_text() == "x"
    dockerfile = (out / "environment" / "Dockerfile").read_text()
    assert dockerfile.startswith(DEFAULT_BASE_DOCKERFILE)
    assert "COPY repo/ /app/" in dockerfile and "RUN bash /pg/prepare.sh" in dockerfile
    assert dockerfile.rstrip().endswith('ENV PATH="/pg/shims:${PATH}"')
    test_sh = (out / "tests" / "test.sh").read_text()
    assert "bash /tests/check.sh" in test_sh and "/logs/verifier/reward.txt" in test_sh
    assert (out / "tests" / "check.sh").read_text().endswith("cd /app\npython3 -m pytest -q\n")
    assert (out / "tests" / "test.sh").stat().st_mode & 0o111
    cfg = tomllib.loads((out / "task.toml").read_text())
    assert cfg["task"]["name"] == "pg/fix-it"
    assert cfg["agent"]["timeout_sec"] == 900
    assert cfg["environment"]["network_mode"] == "allowlist"
    assert cfg["environment"]["allowed_hosts"] == []


def test_network_allow_and_custom_base(tmp_path: Path):
    (tmp_path / ".proving-ground").mkdir()
    (tmp_path / ".proving-ground" / "Dockerfile.base").write_text("FROM node:22\n")
    out = compile_task(
        sc(network={"allow": ["registry.npmjs.org"]}), tmp_path, snap(tmp_path), tmp_path / "t"
    )
    assert (
        (out / "environment" / "Dockerfile").read_text().startswith("FROM node:22\n\nWORKDIR /app")
    )
    cfg = tomllib.loads((out / "task.toml").read_text())
    assert cfg["environment"]["allowed_hosts"] == ["registry.npmjs.org"]


def test_hidden_checks_are_copied_to_tests_not_repo(tmp_path: Path):
    checks = tmp_path / ".proving-ground" / "checks"
    checks.mkdir(parents=True)
    (checks / "verify.py").write_text("print('ok')")
    out = compile_task(
        sc(check="python3 /tests/checks/verify.py"), tmp_path, snap(tmp_path), tmp_path / "t"
    )
    assert (out / "tests" / "checks" / "verify.py").is_file()
    assert not (out / "environment" / "repo" / ".proving-ground").exists()


def test_setup_runs_before_file_faults(tmp_path: Path):
    s = sc(
        kind="failure",
        setup="python3 seed.py",
        faults=[
            {"file": {"path": "config/prod.yaml", "remove": True}},
            {"file": {"path": "data.csv", "truncate": True}},
            {"file": {"path": "db.sqlite", "corrupt": True}},
        ],
    )
    out = compile_task(s, tmp_path, snap(tmp_path), tmp_path / "t")
    prep = (out / "environment" / "pg" / "prepare.sh").read_text().splitlines()
    assert prep[:3] == ["#!/bin/bash", "set -euo pipefail", "cd /app"]
    i_setup = prep.index("python3 seed.py")
    assert prep.index("rm -rf -- config/prod.yaml") > i_setup
    assert ": > data.csv" in prep
    assert any(line.startswith('head -c "$(stat -c%s db.sqlite)"') for line in prep)


def test_command_shims_grouped_by_command(tmp_path: Path):
    s = sc(
        kind="failure",
        faults=[
            {"command": {"match": "npm install", "exit": 2, "stderr": "ERR! network"}},
            {"command": {"match": "npm ci"}},
            {"command": {"match": "curl"}},
        ],
    )
    out = compile_task(s, tmp_path, snap(tmp_path), tmp_path / "t")
    shims = out / "environment" / "pg" / "shims"
    assert sorted(p.name for p in shims.iterdir()) == ["curl", "npm"]
    npm = (shims / "npm").read_text()
    assert '[[ "$args" == install || "$args" == \'install \'* ]]' in npm
    assert "exit 2" in npm and "ERR! network" in npm and "exit 1" in npm
    assert "if true; then" in (shims / "curl").read_text()


def test_overload_inputs_and_context_fill(tmp_path: Path):
    s = snap(tmp_path)
    (s / "CLAUDE.md").write_text("# Rules\nBe brief.\n")
    sc_over = sc(
        kind="overload",
        load={"inputs": {"generate": "tickets", "count": 3}, "context_fill": 2000, "timeout": 120},
    )
    out = compile_task(sc_over, tmp_path, s, tmp_path / "t")
    repo = out / "environment" / "repo"
    assert len(list((repo / "pg_inputs" / "tickets").iterdir())) == 3
    assert len((repo / "PG_CONTEXT.md").read_text()) >= 8000
    assert (repo / "CLAUDE.md").read_text() == "# Rules\nBe brief.\n\n@PG_CONTEXT.md\n"
    assert tomllib.loads((out / "task.toml").read_text())["agent"]["timeout_sec"] == 120
    assert (s / "CLAUDE.md").read_text() == "# Rules\nBe brief.\n"  # snapshot untouched


@pytest.mark.parametrize(
    "fault,message",
    [
        ({"http": {"host": "api.stripe.com", "status": 503}}, "http faults are not supported yet"),
        ({"file": {"path": "a", "unreadable": True}}, "agent runs as root"),
    ],
)
def test_unsupported_faults(tmp_path: Path, fault, message):
    with pytest.raises(UnsupportedFaultError, match=message):
        compile_task(sc(kind="failure", faults=[fault]), tmp_path, snap(tmp_path), tmp_path / "t")


def test_rejects_paths_outside_repo_and_missing_check(tmp_path: Path):
    bad = sc(kind="failure", faults=[{"file": {"path": "../etc/passwd", "remove": True}}])
    with pytest.raises(ValueError, match="relative to the repo root"):
        compile_task(bad, tmp_path, snap(tmp_path), tmp_path / "t")
    with pytest.raises(ValueError, match="needs a check"):
        compile_task(sc(check=None), tmp_path, snap(tmp_path), tmp_path / "t2")


def test_scenario_fixtures_are_copied_into_the_repo(tmp_path: Path):
    fx = tmp_path / ".proving-ground" / "fixtures" / "fix-it"
    fx.mkdir(parents=True)
    (fx / "tickets.json").write_text("[]")
    other = tmp_path / ".proving-ground" / "fixtures" / "other"
    other.mkdir()
    (other / "x.json").write_text("{}")
    out = compile_task(sc(), tmp_path, snap(tmp_path), tmp_path / "t")
    repo = out / "environment" / "repo"
    assert (repo / "pg_fixtures" / "tickets.json").read_text() == "[]"
    assert not (repo / "pg_fixtures" / "x.json").exists()


def test_multi_line_checks_fail_on_the_first_failing_command(tmp_path: Path):
    out = compile_task(sc(check="false\ntrue"), tmp_path, snap(tmp_path), tmp_path / "t")
    check = out / "tests" / "check.sh"
    assert check.read_text().splitlines()[:2] == ["#!/bin/bash", "set -eo pipefail"]
    script = check.read_text().replace("cd /app", "cd .")
    assert subprocess.run(["bash", "-c", script], cwd=tmp_path).returncode == 1


def test_other_agents_are_installed_in_the_image(tmp_path: Path):
    out = compile_task(sc(), tmp_path, snap(tmp_path), tmp_path / "t", agent="codex")
    dockerfile = (out / "environment" / "Dockerfile").read_text()
    assert "@openai/codex@0.162.1" in dockerfile
    assert dockerfile.index("@openai/codex") < dockerfile.index("COPY repo/")
    claude = compile_task(sc(), tmp_path, snap(tmp_path), tmp_path / "t2")
    assert "npm install" not in (claude / "environment" / "Dockerfile").read_text()
