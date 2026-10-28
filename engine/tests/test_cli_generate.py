from pathlib import Path

from typer.testing import CliRunner

from proving_ground.cli import app
from proving_ground.generate.client import ToolCall

cli = CliRunner()
MIX = "typical=1,failure=1,imaginary=1"


def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "app.py").write_text("print('hi')\n")
    return root


def test_needs_sources_or_a_use_case(tmp_path: Path):
    r = cli.invoke(app, ["generate", "--dry-run", "--root", str(project(tmp_path))])
    assert r.exit_code == 1
    assert "Run `pg intake` or pass --use-case" in r.output


def test_bad_mix(tmp_path: Path):
    r = cli.invoke(app, ["generate", "--mix", "typical=x", "--root", str(project(tmp_path))])
    assert r.exit_code == 1
    assert "bad mix entry 'typical=x'" in r.output


def test_dry_run_needs_no_key_and_calls_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr("proving_ground.generate.client.make_client", lambda: 1 / 0)
    root = project(tmp_path)
    assert cli.invoke(app, ["intake", str(root)]).exit_code == 0
    r = cli.invoke(
        app, ["generate", "--dry-run", "--use-case", "Handle refunds.", "--root", str(root)]
    )
    assert r.exit_code == 0, r.output
    assert "Would send: repo:proj/, usecase:use-case" in r.output
    assert "Asking for: 4 typical, 2 edge, 2 adversarial, 2 failure, 1 overload, 2 imaginary" in (
        r.output
    )
    r = cli.invoke(app, ["generate", "--use-case", "Handle refunds.", "--root", str(root)])
    assert r.exit_code == 1
    assert "Set ANTHROPIC_API_KEY first" in r.output


def test_generate_end_to_end_with_fake_client(tmp_path: Path, monkeypatch, plan_data):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")

    class Fake:
        def call(self, prompt, tool, model, max_tokens):
            return ToolCall(plan_data, "tool_use", 100, 200)

    monkeypatch.setattr("proving_ground.generate.client.make_client", Fake)
    root = project(tmp_path)
    args = ["generate", "--use-case", "Handle refunds.", "--mix", MIX, "--root", str(root)]
    r = cli.invoke(app, args)
    assert r.exit_code == 0, r.output
    assert "Workflow support: Support tickets (2 steps)" in r.output
    assert "  config-missing  failure  Config file is gone" in r.output
    assert "Suggested skill: tdd. Fixes need tests" in r.output
    assert "Tokens: 100 in, 200 out." in r.output
    listed = cli.invoke(app, ["scenarios", "list", "--root", str(root)])
    assert "refund-basic  typical  unreviewed  needs approval" in listed.output
    again = cli.invoke(app, args)
    assert again.exit_code == 1
    assert "already exists" in again.output


def test_rejected_output_says_nothing_was_written(tmp_path: Path, monkeypatch, plan_data):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    plan_data["scenarios"].pop()

    class Fake:
        def call(self, *a):
            return ToolCall(plan_data, "tool_use", 1, 1)

    monkeypatch.setattr("proving_ground.generate.client.make_client", Fake)
    root = project(tmp_path)
    r = cli.invoke(app, ["generate", "--use-case", "x", "--mix", MIX, "--root", str(root)])
    assert r.exit_code == 1
    assert "expected 1 imaginary tasks, got 0" in r.output
    assert "Nothing was written." in r.output
