"""`rig gate --metric`: the gate decided on tokens, cost or time, with the pass rate as the
guard, as `rig run --metric` scores a run; the same refusals, cost on a local model included."""

from types import SimpleNamespace

import pytest
from test_gate import skill
from typer.testing import CliRunner

import proving_ground.runner.harbor as harbor
from proving_ground import gate
from proving_ground import local_models as lm
from proving_ground.cli import app

cli = CliRunner()


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """Every trial passes; `tokens(with_skill)` says how many tokens a trial used."""
    monkeypatch.setattr(gate, "HOME", tmp_path / "home")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")

    def use(tokens, size=None):
        if size is not None:  # enough pairs for the pass-rate guard to decide
            monkeypatch.setattr(gate, "trial_count", lambda b, s: size)

        def run(req):
            nop = req.agent == "nop"
            return SimpleNamespace(
                exception_info=None,
                verifier_result=SimpleNamespace(rewards={"reward": 0.0 if nop else 1.0}),
                agent_result=SimpleNamespace(
                    n_input_tokens=0 if nop else tokens(bool(req.skills)),
                    n_output_tokens=0,
                    cost_usd=0.0001,
                ),
                started_at=None,
                finished_at=None,
                trial_name="fake",
            )

        monkeypatch.setattr(harbor, "harbor_executor", run)

    return use


def gate_cmd(tmp_path, *extra):
    return cli.invoke(
        app, ["gate", "-t", str(skill(tmp_path)), "--bench", "bugfix", "--budget", "50", *extra]
    )


def test_a_saving_whose_guard_holds_passes(tmp_path, fake):
    fake(lambda with_skill: 500 if with_skill else 1500, size=80)
    r = gate_cmd(tmp_path, "--metric", "tokens")
    assert r.exit_code == 0, r.stdout
    assert "Gate PASS" in r.stdout
    assert "Scored on: Tokens per Solved Task" in r.stdout
    assert "Verdict on tokens: Helps" in r.stdout
    assert "Saving: Tokens per Solved Task: with 500 vs without 1.5k (-67%" in r.stdout
    assert "Guard: Pass rate: " in r.stdout and "Pass-rate verdict: inconclusive" in r.stdout


def test_more_tokens_fails(tmp_path, fake):
    fake(lambda with_skill: 4500 if with_skill else 1500, size=80)
    r = gate_cmd(tmp_path, "--metric", "tokens")
    assert r.exit_code == 1, r.stdout
    assert "Gate FAIL" in r.stdout and "Reason: On tokens: Doesn't Help." in r.stdout


def test_a_pilot_is_too_small_for_the_guard_so_undecided(tmp_path, fake):
    fake(lambda with_skill: 500 if with_skill else 1500)
    r = gate_cmd(tmp_path, "--metric", "tokens")
    assert r.exit_code == 2, r.stdout
    assert "Reason: On tokens: Can't Tell Yet." in r.stdout
    # The PR comment says what decided it.
    md = gate_cmd(tmp_path, "--metric", "tokens", "--format", "github-md").stdout
    assert "| Scored on | Tokens per Solved Task |" in md
    assert "the verdict on tokens is helps (the pass rate as its guard)" in md


def test_refusals(tmp_path, fake, monkeypatch):
    fake(lambda with_skill: 1000)
    r = gate_cmd(tmp_path, "--metric", "speed")
    assert r.exit_code == 2 and "--metric is one of pass_rate, tokens, cost, time" in r.stdout
    monkeypatch.setattr(lm, "speaks_anthropic", lambda base, http=None: True)
    cli.invoke(app, ["local", "add", "http://127.0.0.1:11434", "qwen3:8b", "--kind", "ollama"])
    r = gate_cmd(tmp_path, "--metric", "cost", "--local-model", "ollama-11434-qwen3-8b")
    assert r.exit_code == 2 and "cost per solved task can't be compared" in r.stdout
    assert not (tmp_path / "home" / "benches").exists()  # refused before anything ran


def test_the_pass_rate_gate_is_unchanged(tmp_path, fake):
    fake(lambda with_skill: 1000)
    r = gate_cmd(tmp_path)
    assert "Scored on" not in r.stdout and "  Verdict: " in r.stdout


def test_a_full_gate_on_a_saving_plans_the_guards_pairs(tmp_path, fake):
    from proving_ground import rig_score as rig_mod

    fake(lambda with_skill: 500 if with_skill else 1500)
    r = gate_cmd(tmp_path, "--metric", "tokens", "--size", "full")
    assert r.exit_code == 0, r.stdout
    # The guard's pairs, rounded up to whole repeats of the bench's five tasks.
    assert rig_mod.metric_guard_pairs() <= 40
    assert "Pairs: 40" in r.stdout and "Verdict on tokens: Helps" in r.stdout
