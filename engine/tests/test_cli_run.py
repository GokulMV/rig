from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from proving_ground.cli import app
from proving_ground.files import save_scenario
from proving_ground.models import Scenario

cli = CliRunner()


def skill(tmp_path: Path) -> Path:
    d = tmp_path / "skills" / "tdd"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: tdd\n---\nWrite the test first.\n")
    return d


def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "app.py").write_text("x")
    save_scenario(
        root, Scenario(id="a", instruction="Fix it.", check="true", check_status="approved")
    )
    return root


def fake_result(reward):
    return SimpleNamespace(
        exception_info=None,
        verifier_result=SimpleNamespace(rewards={"reward": reward}),
        agent_result=SimpleNamespace(n_input_tokens=10, n_output_tokens=5, cost_usd=0.5),
        started_at=None,
        finished_at=None,
        trial_name="t",
    )


def test_run_requires_api_key(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    r = cli.invoke(
        app, ["run", "-t", str(skill(tmp_path)), "--budget", "5", "--root", str(project(tmp_path))]
    )
    assert r.exit_code == 1
    assert "Set ANTHROPIC_API_KEY" in r.output


def test_run_end_to_end_with_fake_harbor(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    def executor(req):
        if req.agent == "nop":
            return fake_result(0.0)
        return fake_result(1.0 if req.skills else 0.0)

    monkeypatch.setattr("proving_ground.runner.harbor.harbor_executor", executor)
    root = project(tmp_path)
    r = cli.invoke(
        app, ["run", "-t", str(skill(tmp_path)), "--budget", "100", "--n", "6", "--root", str(root)]
    )
    assert r.exit_code == 0, r.output
    assert "Experiment 1: tdd on claude-sonnet-5-5, 6 repeats x 1 scenarios" in r.output
    assert "Verdict: HELPS" in r.output
    task = root / ".proving-ground" / "runs" / "1" / "tasks" / "a"
    assert (task / "task.toml").is_file()
    assert (root / ".proving-ground" / "runs" / "1" / "meta.json").is_file()


def test_resume_refuses_changed_skill(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(
        "proving_ground.runner.harbor.harbor_executor",
        lambda req: fake_result(1.0 if req.agent != "nop" else 0.0),
    )
    root, sk = project(tmp_path), skill(tmp_path)
    assert (
        cli.invoke(
            app, ["run", "-t", str(sk), "--budget", "0.6", "--n", "4", "--root", str(root)]
        ).exit_code
        == 0
    )
    (sk / "SKILL.md").write_text("changed")
    r = cli.invoke(
        app, ["run", "-t", str(sk), "--budget", "9", "--resume", "1", "--root", str(root)]
    )
    assert r.exit_code == 1
    assert "tdd changed since experiment 1" in r.output


@pytest.mark.parametrize(
    "args,msg",
    [(["--kind", "edge"], "No tasks match."), (["--scenario", "zzz"], "No tasks match.")],
)
def test_filters(tmp_path: Path, monkeypatch, args, msg):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    r = cli.invoke(
        app,
        [
            "run",
            "-t",
            str(skill(tmp_path)),
            "--budget",
            "5",
            "--root",
            str(project(tmp_path)),
            *args,
        ],
    )
    assert r.exit_code == 1 and msg in r.output
