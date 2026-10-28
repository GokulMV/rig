"""`rig run --before ... --after ...`: a code change measured before and after from the command
line, on the same path as the API (beforeafter.resolve, then prepare_experiment with the
change), with the same refusals."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from proving_ground import skills
from proving_ground.cli import app
from proving_ground.files import ensure_pg_dir, save_scenario
from proving_ground.models import Scenario

cli = CliRunner()
V = skills.value("measurability", "before_after")


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def make_repo(root: Path) -> Path:
    """v1 on main; a `split` branch that moves the limits into their own module."""
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    (root / "app.py").write_text("LIMIT = 100\n")
    ensure_pg_dir(root)
    save_scenario(root, Scenario(id="a", instruction="Fix.", check="true", check_status="approved"))
    git(root, "add", "-A")
    git(root, "commit", "-qm", "v1")
    git(root, "checkout", "-q", "-b", "split")
    (root / "app.py").write_text("from limits import LIMIT\n")
    (root / "limits.py").write_text("LIMIT = 100\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "split the limits out")
    git(root, "checkout", "-q", "main")
    return root


def fake_result(reward: float):
    return SimpleNamespace(
        exception_info=None,
        verifier_result=SimpleNamespace(rewards={"reward": reward}),
        agent_result=SimpleNamespace(n_input_tokens=10, n_output_tokens=5, cost_usd=0.1),
        started_at=None,
        finished_at=None,
        trial_name="t",
    )


@pytest.fixture
def repo(tmp_path: Path, monkeypatch):
    """A repo, and a fake Harbor whose agent passes only on the after code (tasks-with/)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    seen: list[tuple[str, str]] = []

    def executor(req):
        code = (req.task_dir / "environment" / "repo" / "app.py").read_text()
        seen.append((req.task_dir.parent.name, code))
        if req.agent == "nop":
            return fake_result(0.0)
        return fake_result(1.0 if req.task_dir.parent.name == "tasks-with" else 0.0)

    monkeypatch.setattr("proving_ground.runner.harbor.harbor_executor", executor)
    return make_repo(tmp_path / "repo"), seen


def run(root: Path, *args: str):
    return cli.invoke(app, ["run", *args, "--budget", "100", "--n", "4", "--root", str(root)])


def test_a_branch_runs_against_the_commit_before(repo):
    root, seen = repo
    r = run(root, "--before", "HEAD", "--after", "split")
    assert r.exit_code == 0, r.output
    main, split = git(root, "rev-parse", "main"), git(root, "rev-parse", "split")
    name = f"HEAD ({main[:7]}) → split ({split[:7]})"
    assert f"Experiment 1: {name} on claude-sonnet-5-5, 4 repeats x 1 scenarios" in r.output
    assert V["compare"].format(base=f"HEAD ({main[:7]})", after=f"split ({split[:7]})") in r.output
    assert "2 files differ" in r.output
    # The trials and the summary name the arms After and Before.
    assert "a  after    #0  pass" in r.output and "a  before   #0  fail" in r.output
    assert "After: 100.0%   Before: 0.0%   Pairs: 4" in r.output
    assert "Cost: $0.40 after, $0.40 before" in r.output
    assert "Verdict: HELPS" in r.output
    assert "uncommitted changes are not included" not in r.output
    # Each arm ran its own commit's code; the checkout never moved.
    assert {code for arm, code in seen if arm == "tasks"} == {"LIMIT = 100\n"}
    assert {code for arm, code in seen if arm == "tasks-with"} == {"from limits import LIMIT\n"}
    meta = json.loads((root / ".proving-ground" / "runs" / "1" / "meta.json").read_text())
    assert meta["before_after"]["base"]["sha"] == main
    assert meta["before_after"]["after"]["sha"] == split
    assert git(root, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    # `rig report` names the arms the same way.
    rep = cli.invoke(app, ["report", "1", "--root", str(root)])
    assert rep.exit_code == 0, rep.output
    assert "(before_after," in rep.output
    assert "After: 100.0%   Before: 0.0%   Pairs: 4" in rep.output


def test_after_left_out_is_the_uncommitted_working_tree(repo):
    root, seen = repo
    (root / "app.py").write_text("LIMIT = 'edited'\n")
    r = run(root, "--before", "HEAD")
    assert r.exit_code == 0, r.output
    assert f"→ {V['working_tree']} on" in r.output
    assert {code for arm, code in seen if arm == "tasks-with"} == {"LIMIT = 'edited'\n"}
    assert {code for arm, code in seen if arm == "tasks"} == {"LIMIT = 100\n"}
    meta = json.loads((root / ".proving-ground" / "runs" / "1" / "meta.json").read_text())
    assert meta["before_after"]["after"]["working_tree"] is True
    # --after alone measures against HEAD.
    r = run(root, "--after", "split")
    assert r.exit_code == 0, r.output
    assert "Experiment 2: HEAD (" in r.output


def test_refusals_come_first_and_write_nothing(repo, tmp_path: Path, monkeypatch):
    root, seen = repo
    monkeypatch.delenv("ANTHROPIC_API_KEY")  # refused for what it is, not for the sign-in
    for args, why in (
        (["--before", "HEAD", "--after", "main"], "has the same code as"),
        (["--before", "HEAD"], "has the same code as"),  # a clean checkout
        (["--before", "nope", "--after", "split"], "nope isn't a commit or branch"),
        (["--after", "--output=/tmp/x"], "isn't a commit or branch"),
        (["-t", str(root), "--before", "HEAD"], "either -t (an agent change) or --before"),
        ([], "Pick a change to measure"),
    ):
        r = run(root, *args)
        assert r.exit_code == 1, (args, r.output)
        assert why in r.output, (args, r.output)
    assert not (root / ".proving-ground" / "runs").exists() and not seen
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "a.py").write_text("x")
    r = run(plain, "--before", "HEAD")
    assert r.exit_code == 1 and V["not_git"] in r.output.replace("\n", " ")
