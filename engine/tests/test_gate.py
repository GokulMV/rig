"""`pg gate`: exit codes with a fake executor, and the three report formats."""

import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import proving_ground.runner.harbor as harbor
from proving_ground import gate
from proving_ground.cli import app

cli = CliRunner()


def skill(tmp_path: Path) -> Path:
    d = tmp_path / "skills" / "tdd"
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("---\nname: tdd\ndescription: test first\n---\nTest first.\n")
    return d


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "HOME", tmp_path / "home")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)

    def use(reward, cost=0.02):
        def run(req):
            r = 0.0 if req.agent == "nop" else reward(req)
            return SimpleNamespace(
                exception_info=None,
                verifier_result=SimpleNamespace(rewards={"reward": r}),
                agent_result=SimpleNamespace(n_input_tokens=10, n_output_tokens=5, cost_usd=cost),
                started_at=None,
                finished_at=None,
                trial_name="fake",
            )

        monkeypatch.setattr(harbor, "harbor_executor", run)

    return use


def gate_cmd(tmp_path, *extra):
    return cli.invoke(app, ["gate", "-t", str(skill(tmp_path)), "--bench", "bugfix", *extra])


def test_exit_0_when_it_helps(tmp_path, fake):
    fake(lambda req: 1.0 if req.skills else 0.0)
    r = gate_cmd(tmp_path)
    assert r.exit_code == 0, r.output
    assert "Gate PASS" in r.stdout and "Verdict: helps" in r.stdout
    assert "Adherence not checked" in r.stdout  # a plain skill has no steps to follow


def test_exit_1_when_it_hurts(tmp_path, fake):
    fake(lambda req: 0.0 if req.skills else 1.0)
    r = gate_cmd(tmp_path)
    assert r.exit_code == 1, r.output
    assert "Gate FAIL" in r.stdout and "It hurts" in r.stdout


def test_min_delta_decides_when_the_verdict_is_open(tmp_path, fake):
    fake(lambda req: 1.0)  # no difference: inconclusive, 0 pts
    assert gate_cmd(tmp_path, "--min-delta", "0").exit_code == 0
    r = gate_cmd(tmp_path, "--min-delta", "5")
    assert r.exit_code == 1 and "under the minimum" in r.stdout


def test_exit_2_when_the_budget_stops_it_before_deciding(tmp_path, fake):
    fake(lambda req: 1.0, cost=1.0)
    r = gate_cmd(tmp_path, "--budget", "0.5")
    assert r.exit_code == 2, r.output
    assert "UNDECIDED" in r.stdout


def test_exit_2_without_credentials_and_for_a_broken_bench(tmp_path, fake, monkeypatch):
    fake(lambda req: 1.0)
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    r = gate_cmd(tmp_path)
    assert r.exit_code == 2 and "ANTHROPIC_API_KEY" in r.stdout
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    r = cli.invoke(app, ["gate", "-t", str(skill(tmp_path)), "--bench", "nope"])
    assert r.exit_code == 2 and "No bench" in r.stdout


def test_exit_2_when_the_sandbox_breaks(tmp_path, fake):
    def boom(req):
        raise RuntimeError("docker is down")

    fake(boom)
    r = gate_cmd(tmp_path)
    assert r.exit_code == 2, r.output


def test_adherence_below_the_minimum_fails():
    r = gate.GateResult(2, "w", "b", "claude-code", "m", {"budget": 1.0})
    r.verdict, r.diff, r.ci_low, r.ci_high, r.pairs = "helps", 0.4, 0.1, 0.7, 5
    r.adherence = {"followed": 2, "read": 5}
    assert gate.decide(r, 0, 0.85, False).code == 1
    assert "2 of 5" in r.reasons[0]
    r2 = gate.GateResult(2, "w", "b", "claude-code", "m", {"budget": 1.0})
    r2.verdict, r2.diff, r2.ci_low, r2.ci_high = "helps", 0.4, 0.1, 0.7
    r2.adherence = {"followed": 5, "read": 5}
    assert gate.decide(r2, 0, 0.85, False).code == 0
    r3 = gate.GateResult(2, "w", "b", "claude-code", "m", {"budget": 1.0})
    r3.verdict, r3.diff, r3.ci_low, r3.ci_high = "helps", 0.4, 0.1, 0.7
    r3.adherence = {"followed": 0, "read": 0}  # no logs: warn, don't fail
    assert gate.decide(r3, 0, 0.85, False).code == 0 and r3.warnings


def test_report_formats_and_out_file(tmp_path, fake, monkeypatch):
    # One scenario is worse with the skill: it fails its testcase, though the whole gate passes.
    fake(lambda req: 0.0 if req.skills and "rounding" in str(req.task_dir) else 1.0)
    out = tmp_path / "gate.xml"
    r = gate_cmd(tmp_path, "--format", "junit", "--out", str(out), "--min-delta", "-100")
    assert r.exit_code == 0, r.output
    suite = ET.parse(out).getroot()
    assert suite.tag == "testsuite" and suite.get("tests") == "5"
    cases = suite.findall("testcase")
    assert len(cases) == 5
    assert {c.get("name") for c in cases} >= {"rounding", "coupon-case"}
    assert suite.get("failures") == "1"
    assert [c.get("name") for c in cases if c.find("failure") is not None] == ["rounding"]

    monkeypatch.setattr(gate, "HOME", tmp_path / "home2")  # not the first run's shared baseline
    fake(lambda req: 1.0 if req.skills else 0.0)
    md = gate_cmd(tmp_path, "--format", "github-md").stdout
    assert md.startswith("## ✅ Rig gate: PASS")
    assert "| Verdict | helps |" in md and "| Task | With | Without | |" in md
    assert "| rounding | 1/1 | 0/1 | ok |" in md

    text = gate_cmd(tmp_path, "--format", "text").stdout
    assert "Gate PASS: tdd on bugfix" in text and "ok   rounding: with 1/1, without 0/1" in text
    assert gate_cmd(tmp_path, "--format", "html").exit_code == 2
