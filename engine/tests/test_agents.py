from pathlib import Path

import pytest

from proving_ground.agents import AGENTS, FLAG_ON, Credentials, agent, install_snippet


def test_registry_has_the_four_agents_with_harbor_names():
    assert [a.id for a in AGENTS] == ["claude-code", "codex", "opencode", "gemini-cli"]
    assert agent("codex").label == "Codex"
    with pytest.raises(KeyError):
        agent("nope")


def test_status_detects_env_keys_and_login_files(tmp_path: Path):
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "auth.json").write_text("{}")
    creds = Credentials(env={"ANTHROPIC_API_KEY": "sk-x"}, home=tmp_path)
    claude = {o["id"]: o for o in creds.status("claude-code")}
    assert (
        claude["api-key"]["ready"] is True
        and claude["api-key"]["how"] == "ANTHROPIC_API_KEY is set"
    )
    assert claude["subscription"]["ready"] is False
    codex = {o["id"]: o for o in creds.status("codex")}
    assert codex["login"]["ready"] is True and codex["api-key"]["ready"] is False
    assert creds.ready("codex") and creds.ready("claude-code") and not creds.ready("gemini-cli")


def test_keys_typed_in_the_page_stay_in_memory_and_win(tmp_path: Path):
    creds = Credentials(env={}, home=tmp_path)
    creds.set("claude-code", "subscription", "oauth-token-123")
    env = creds.env_for("claude-code")
    assert env == {"CLAUDE_CODE_OAUTH_TOKEN": "oauth-token-123", "CLAUDE_FORCE_OAUTH": FLAG_ON}
    assert all("oauth-token-123" not in str(o) for o in creds.status("claude-code"))  # never echoed
    creds.clear("claude-code")
    assert creds.env_for("claude-code") == {}


def test_login_files_turn_into_harbor_flags(tmp_path: Path):
    (tmp_path / ".gemini").mkdir()
    (tmp_path / ".gemini" / "oauth_creds.json").write_text("{}")
    creds = Credentials(env={}, home=tmp_path)
    assert creds.env_for("gemini-cli") == {"GEMINI_FORCE_OAUTH": FLAG_ON}


def test_unknown_option_is_refused(tmp_path: Path):
    with pytest.raises(ValueError, match="no sign-in option"):
        Credentials(env={}, home=tmp_path).set("codex", "subscription", "x")


def test_install_snippets_pin_versions_and_skip_claude():
    assert install_snippet("claude-code") == ""
    assert "@openai/codex@0.162.1" in install_snippet("codex")
    assert "opencode-ai@1.18.35" in install_snippet("opencode")
    assert "@google/gemini-cli@0.63.0" in install_snippet("gemini-cli")


def test_claude_host_login_reads_auth_status():
    import subprocess

    from proving_ground.agents import claude_host_login

    def run(cmd, **kw):
        assert cmd == ["claude", "auth", "status", "--json"]
        return subprocess.CompletedProcess(
            cmd, 0, '{"loggedIn": true, "email": "a@b.c", "subscriptionType": "max"}', ""
        )

    assert claude_host_login(run) == {"email": "a@b.c", "plan": "max", "method": None}
    out = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, '{"loggedIn": false}', "")  # noqa: E731
    assert claude_host_login(out) is None


def test_token_login_reads_the_token_from_a_terminal(tmp_path):
    import time

    from proving_ground.agents import CliLogin, Credentials

    fake = tmp_path / "fake-claude"
    # Built at runtime so nothing shaped like a real token sits in the source, where secret
    # scanners would flag it. TOKEN needs the real prefix to recognise it.
    token = "-".join(["sk", "ant", "oat01", "FAKE_not_a_real_token_0123456789-xyz"])
    # Like the real CLI: colours, a link to approve, then the token.
    fake.write_text(
        "#!/bin/sh\n"
        "printf '\\033[1mOpen this link:\\033[0m https://claude.ai/oauth/authorize?code=xyz\\n'\n"
        "sleep 0.3\n"
        f"printf 'Your token: \\033[32m{token}\\033[0m\\n'\n"
        "sleep 5\n"
    )
    fake.chmod(0o755)
    creds = Credentials(env={}, home=tmp_path)
    job = CliLogin(creds, "claude-code", cmd=[str(fake)], timeout=20)
    assert job.start()["state"] == "running"
    for _ in range(100):
        if job.state != "running":
            break
        time.sleep(0.05)
    assert job.state == "done"
    assert job.url == "https://claude.ai/oauth/authorize?code=xyz"
    assert creds.ready("claude-code")
    assert creds.env_for("claude-code")["CLAUDE_CODE_OAUTH_TOKEN"] == token
    assert "sk-ant" not in str(job.view())  # the token is never in what the API returns


def test_token_login_without_a_token_is_an_error(tmp_path):
    import time

    from proving_ground.agents import CliLogin, Credentials

    fake = tmp_path / "fake-claude"
    fake.write_text("#!/bin/sh\necho 'cancelled'\n")
    fake.chmod(0o755)
    job = CliLogin(Credentials(env={}, home=tmp_path), "claude-code", cmd=[str(fake)], timeout=20)
    job.start()
    for _ in range(100):
        if job.state != "running":
            break
        time.sleep(0.05)
    assert job.state == "error" and "without finishing" in job.error


def test_cli_login_that_writes_a_file(tmp_path):
    """Like `codex login`: shows a link, then writes ~/.codex/auth.json."""
    import time

    from proving_ground.agents import CliLogin, Credentials

    fake = tmp_path / "fake-codex"
    fake.write_text(
        "#!/bin/sh\necho 'Open https://auth.openai.com/x to sign in'\nsleep 0.3\n"
        f"mkdir -p {tmp_path}/.codex && echo '{{}}' > {tmp_path}/.codex/auth.json\nsleep 5\n"
    )
    fake.chmod(0o755)
    creds = Credentials(env={}, home=tmp_path)
    assert not creds.ready("codex")
    job = CliLogin(creds, "codex", cmd=[str(fake)], timeout=20)
    job.start()
    for _ in range(100):
        if job.state != "running":
            break
        time.sleep(0.05)
    assert job.state == "done" and job.url.startswith("https://auth.openai.com")
    assert creds.ready("codex")


def test_cli_login_missing_cli_says_how_to_install(tmp_path):
    from proving_ground.agents import CliLogin, Credentials

    job = CliLogin(Credentials(env={}, home=tmp_path), "codex", cmd=["no-such-cli-here"])
    v = job.start()
    assert v["state"] == "error" and "npm install -g @openai/codex@0.162.1" in v["error"]


def test_manual_login_watches_for_the_file(tmp_path):
    import time

    from proving_ground.agents import CliLogin, Credentials

    job = CliLogin(Credentials(env={}, home=tmp_path), "gemini-cli", timeout=20)
    v = job.start()
    assert v["state"] == "running" and "Login with Google" in v["manual"]
    (tmp_path / ".gemini").mkdir()
    (tmp_path / ".gemini" / "oauth_creds.json").write_text("{}")
    for _ in range(40):
        if job.state != "running":
            break
        time.sleep(0.1)
    assert job.state == "done"


def test_sign_in_flags_read_as_on_and_leave_the_logs_alone():
    """Harbor scrubs secret-looking env values (…AUTH…) out of a trial's logs. A plain "1" there
    blanked every 1 in them (Try it's answers and costs went missing); FLAG_ON is read as on and
    never matches anything a trial writes."""
    from harbor.utils.env import is_sensitive_env_key, parse_bool_env_value

    line = '{"type":"result","total_cost_usd":0.1635,"duration_ms":56100,"result":"Yes: 1 refund"}'
    for a in AGENTS:
        for s in a.sign_in:
            for key, value in s.flags.items():
                assert parse_bool_env_value(value, name=key) is True
                if is_sensitive_env_key(key):
                    assert value not in line and line.replace(value, "[REDACTED]") == line
    assert line.replace("1", "[REDACTED]") != line  # what the old flag did
