"""`rig run --local-model` and `rig gate --local-model`: Claude Code on a model added with `rig
local add` (or in the app), as the app's runs on one: no API key, free, a longer time limit, the
skill handed over, the record naming the model; `--metric` scores a run on tokens, cost or time,
and cost is refused on a local model. Harbor is faked."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_cli_before_after import git, make_repo
from typer.testing import CliRunner

from proving_ground import gate
from proving_ground import local_models as lm
from proving_ground.cli import app

cli = CliRunner()
LABEL = "qwen3:8b · ollama"


def result(reward: float, tokens: int):
    # The fake agent reports a cost: a local run must still count it as nothing.
    return SimpleNamespace(
        exception_info=None,
        verifier_result=SimpleNamespace(rewards={"reward": reward}),
        agent_result=SimpleNamespace(n_input_tokens=tokens, n_output_tokens=0, cost_usd=0.5),
        started_at=None,
        finished_at=None,
        trial_name="t",
    )


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    """A repo with a skill, no API key, and a home of its own with no local model yet."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(gate, "HOME", tmp_path / "home")
    monkeypatch.setattr(lm, "speaks_anthropic", lambda base, http=None: "11434" in base)
    calls: list = []

    def fake(req):
        calls.append(req)
        if req.agent == "nop":
            return result(0.0, 0)
        # Every trial passes; with the skill (or on the after code) a third of the tokens.
        return result(1.0, 500 if req.skills or req.task_dir.parent.name == "tasks-with" else 1500)

    monkeypatch.setattr("proving_ground.runner.harbor.harbor_executor", fake)
    sk = tmp_path / "skills" / "tdd"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("---\nname: tdd\ndescription: test first\n---\nTest first.\n")
    return SimpleNamespace(root=make_repo(tmp_path / "repo"), sk=sk, calls=calls, home=tmp_path)


def add(*args: str):
    return cli.invoke(app, ["local", "add", *args])


def run(root: Path, *args: str):
    return cli.invoke(app, ["run", *args, "--n", "4", "--root", str(root)])


def meta(root: Path, eid: int) -> dict:
    return json.loads((root / ".proving-ground" / "runs" / str(eid) / "meta.json").read_text())


def test_local_models_are_listed_added_and_removed(env):
    r = cli.invoke(app, ["local", "list"])
    assert r.exit_code == 0 and "No local models yet" in r.output
    r = add("http://127.0.0.1:11434", "qwen3:8b", "--kind", "ollama")
    assert r.exit_code == 0, r.output
    assert f"Added local:ollama-11434-qwen3-8b  {LABEL}: can run Claude Code." in r.output
    r = add("http://127.0.0.1:1234/v1", "phi-4", "--kind", "lmstudio")
    assert "can't run Claude Code (no /v1/messages)" in r.output
    # A public host is refused: nothing you test leaves.
    r = add("https://api.example.com", "gpt")
    assert r.exit_code == 1 and "isn't on this machine or your network" in r.output
    r = cli.invoke(app, ["local", "list"])
    assert (
        f"local:ollama-11434-qwen3-8b  {LABEL}  http://127.0.0.1:11434  can run Claude Code"
        in r.output
    )
    assert (
        "local:lmstudio-1234-phi-4  phi-4 · lmstudio  http://127.0.0.1:1234  can't run" in r.output
    )
    # The app's own list: the same file.
    reg = lm.Registry(env.home / "home" / "local-models.json")
    assert [m.id for m in reg.models()] == [
        "local:ollama-11434-qwen3-8b",
        "local:lmstudio-1234-phi-4",
    ]
    r = cli.invoke(app, ["local", "remove", "lmstudio-1234-phi-4"])  # "local:" may be left out
    assert r.exit_code == 0 and [m.id for m in reg.models()] == ["local:ollama-11434-qwen3-8b"]


def test_a_skill_runs_on_a_local_model_with_no_key_and_no_cost(env):
    add("http://127.0.0.1:11434", "qwen3:8b", "--kind", "ollama")
    r = run(env.root, "-t", str(env.sk), "--local-model", "ollama-11434-qwen3-8b")
    assert r.exit_code == 0, r.output
    assert f"Experiment 1: tdd on {LABEL} (local, free), 4 repeats x 1 scenarios" in r.output
    assert "Cost: $0.00 with, $0.00 without" in r.output  # the fake agent reports $0.50 a trial
    assert "Scored on" not in r.output  # the pass rate: as before
    runs = [q for q in env.calls if q.agent == "claude-code"]
    e = dict(runs[0].env)
    assert e["ANTHROPIC_BASE_URL"] == "http://host.docker.internal:11434"
    assert e["ANTHROPIC_API_KEY"] == "local"
    assert runs[0].model == "qwen3:8b"
    toml = (Path(runs[0].task_dir) / "task.toml").read_text()
    assert "timeout_sec = 1800" in toml  # 3x the 600s task: local models are slow
    m = meta(env.root, 1)
    assert m["local_model"] == "local:ollama-11434-qwen3-8b" and m["local_label"] == LABEL
    assert m["metric"] == "pass_rate" and m["nudge_prompt"] is True
    rep = cli.invoke(app, ["report", "1", "--root", str(env.root)])
    assert f"on {LABEL} (local, free), status done" in rep.output


def test_metric_scores_on_tokens_and_refuses_cost_on_a_local_model(env):
    add("http://127.0.0.1:11434", "qwen3:8b", "--kind", "ollama")
    mid = "local:ollama-11434-qwen3-8b"
    for args, why in (
        (["--metric", "cost"], "cost per solved task can't be compared"),
        (["--metric", "speed"], "--metric is one of pass_rate, tokens, cost, time, not 'speed'"),
    ):
        r = run(env.root, "-t", str(env.sk), "--local-model", mid, *args)
        assert r.exit_code == 1 and why in r.output, r.output
    for args, why in (
        (["--local-model", "nope"], "No local model 'nope'. `rig local list` shows"),
        ([], "Set --budget"),  # on the sign-in, a budget is needed
    ):
        r = run(env.root, "-t", str(env.sk), *args)
        assert r.exit_code == 1 and why in r.output, r.output
    assert not (env.root / ".proving-ground" / "runs").exists() and not env.calls

    r = run(env.root, "-t", str(env.sk), "--local-model", mid, "--metric", "tokens")
    assert r.exit_code == 0, r.output
    assert "Scored on tokens per solved task, with the pass rate as the guard." in r.output
    assert "Tokens per Solved Task: with 500 vs without 1.5k (-67%" in r.output
    assert "Pass rate: 4 of 4 passed with vs 4 of 4 passed without" in r.output
    assert "Verdict on tokens: " in r.output
    assert meta(env.root, 1)["metric"] == "tokens"
    rep = cli.invoke(app, ["report", "1", "--root", str(env.root)])
    assert "Tokens per Solved Task: with 500 vs without 1.5k (-67%" in rep.output


def test_a_code_change_runs_before_and_after_on_a_local_model(env):
    add("http://127.0.0.1:11434", "qwen3:8b", "--kind", "ollama")
    args = ["--before", "HEAD", "--after", "split", "--local-model", "ollama-11434-qwen3-8b"]
    r = run(env.root, *args, "--metric", "time")
    assert r.exit_code == 0, r.output
    assert f"on {LABEL} (local, free)" in r.output and "2 files differ" in r.output
    assert "Scored on time per solved task" in r.output
    m = meta(env.root, 1)
    assert m["before_after"]["after"]["sha"] == git(env.root, "rev-parse", "split")
    assert m["local_model"] == "local:ollama-11434-qwen3-8b" and m["metric"] == "time"
    assert m["nudge_prompt"] is None  # no skill to open


def test_gate_runs_on_a_local_model_with_no_key(env):
    add("http://127.0.0.1:11434", "qwen3:8b", "--kind", "ollama")
    add("http://127.0.0.1:1234", "phi-4", "--kind", "lmstudio")
    t = ["gate", "-t", str(env.sk), "--bench", "bugfix"]
    r = cli.invoke(app, [*t, "--local-model", "local:ollama-11434-qwen3-8b"])
    assert r.exit_code == 0, r.output
    assert f"Gate PASS: tdd on bugfix (claude-code, {LABEL} (local))" in r.stdout
    runs = [q for q in env.calls if q.agent == "claude-code"]
    assert dict(runs[0].env)["ANTHROPIC_BASE_URL"] == "http://host.docker.internal:11434"
    # Broken, not failed: exit 2.
    r = cli.invoke(app, [*t, "--local-model", "lmstudio-1234-phi-4"])
    assert r.exit_code == 2 and "Anthropic's Messages API" in r.output
    r = cli.invoke(app, [*t, "--local-model", "nope"])
    assert r.exit_code == 2 and "No local model 'nope'" in r.output
    r = cli.invoke(app, [*t, "--local-model", "ollama-11434-qwen3-8b", "--agent", "codex"])
    assert r.exit_code == 2 and "runs Claude Code only" in r.output


def test_a_resumed_run_goes_on_on_its_own_local_model_and_metric(env):
    add("http://127.0.0.1:11434", "qwen3:8b", "--kind", "ollama")
    r = run(
        env.root, "-t", str(env.sk), "--local-model", "ollama-11434-qwen3-8b", "--metric", "tokens"
    )
    assert r.exit_code == 0, r.output
    env.calls.clear()
    # No --local-model, no key, no budget: it goes on there, still scored on tokens.
    r = cli.invoke(app, ["run", "-t", str(env.sk), "--resume", "1", "--root", str(env.root)])
    assert r.exit_code == 0, r.output
    assert f"Experiment 1: tdd on {LABEL} (local, free)" in r.output
    assert "Scored on tokens per solved task:" in r.output
    assert all(dict(q.env)["ANTHROPIC_API_KEY"] == "local" for q in env.calls if q.env)


def test_auto_keeps_adding_pairs_until_a_cap_and_says_why(env):
    # Every trial passes in both arms: nothing decides it, so it grows to the looks cap.
    add("http://127.0.0.1:11434", "qwen3:8b", "--kind", "ollama")
    r = run(env.root, "-t", str(env.sk), "--local-model", "ollama-11434-qwen3-8b", "--auto")
    assert r.exit_code == 0, r.output
    assert "Not decided yet at 4 pairs: added a batch (1 so far)." in r.output
    assert "Stopped adding pairs at 9: 5 extra looks." in r.output
    assert len([q for q in env.calls if q.agent == "claude-code"]) == 2 * 9
    # Without --auto the run stays at its planned pairs.
    r = run(env.root, "-t", str(env.sk), "--local-model", "ollama-11434-qwen3-8b")
    assert r.exit_code == 0 and "Not decided yet" not in r.output, r.output
