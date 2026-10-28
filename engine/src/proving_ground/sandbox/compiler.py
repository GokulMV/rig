"""Compile a scenario into a Harbor task directory."""

from __future__ import annotations

import json
import shlex
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from proving_ground.agents import install_snippet
from proving_ground.files import PG_DIR
from proving_ground.models import CommandFault, Scenario, Treatment
from proving_ground.sandbox import treatments as treatment_files
from proving_ground.sandbox.loadgen import context_fill_text, generate_inputs

DEFAULT_BASE_DOCKERFILE = """\
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends \\
    bash ca-certificates curl git procps python3 python3-pip python3-venv \\
 && rm -rf /var/lib/apt/lists/*
# Claude Code is installed at build time so trials can run with restricted network access.
RUN curl -fsSL https://downloads.claude.ai/claude-code-releases/bootstrap.sh | bash \\
 && ln -sf /root/.local/bin/claude /usr/local/bin/claude && claude --version
"""

DOCKERFILE_TAIL = """
WORKDIR /app
COPY repo/ /app/
COPY pg/ /pg/
RUN bash /pg/prepare.sh
ENV PATH="/pg/shims:${PATH}"
"""

TEST_SH = """\
#!/bin/bash
mkdir -p /logs/verifier
cd /app
bash /tests/check.sh > /logs/verifier/check.log 2>&1
code=$?
echo "$code" > /logs/verifier/exit_code.txt
if [ "$code" -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
"""


class UnsupportedFaultError(ValueError):
    pass


@dataclass(frozen=True)
class CompileOptions:
    cpus: int = 2
    memory_mb: int = 4096
    build_timeout_sec: int = 1800
    verifier_timeout_sec: int = 300
    agent_timeout_factor: float = 1.0  # local models are slower: give the agent longer


def base_dockerfile(project_root: Path) -> str:
    custom = project_root / PG_DIR / "Dockerfile.base"
    return custom.read_text() if custom.is_file() else DEFAULT_BASE_DOCKERFILE


def _repo_path(path: str) -> str:
    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"fault path must be relative to the repo root: {path!r}")
    return shlex.quote(p.as_posix())


def _shim(cmd: str, faults: list[CommandFault]) -> str:
    lines = ["#!/bin/bash", f"# Rig fault shim for `{cmd}`", 'args="$*"']
    for f in faults:
        rest = f.match.split(None, 1)[1] if " " in f.match.strip() else ""
        cond = (
            "true"
            if not rest
            else f'[[ "$args" == {shlex.quote(rest)} || "$args" == {shlex.quote(rest + " ")}* ]]'
        )
        msg = f.stderr or f"{cmd}: simulated failure (Rig fault)"
        lines += [
            f"if {cond}; then",
            f"  printf '%s\\n' {shlex.quote(msg)} >&2",
            f"  exit {f.exit}",
            "fi",
        ]
    lines += [
        f'real="$(PATH="${{PATH//\\/pg\\/shims:/}}" command -v {shlex.quote(cmd)})"',
        f'if [ -z "$real" ]; then echo {shlex.quote(cmd + ": command not found")} >&2; exit 127; fi',
        'exec "$real" "$@"',
    ]
    return "\n".join(lines) + "\n"


def _prepare_script(s: Scenario) -> str:
    lines = ["#!/bin/bash", "set -euo pipefail", "cd /app"]
    if s.setup:
        lines += ["# scenario setup", s.setup]
    for f in s.faults:
        if f.file is None:
            continue
        path = _repo_path(f.file.path)
        if f.file.remove:
            lines.append(f"rm -rf -- {path}")
        elif f.file.truncate:
            lines.append(f": > {path}")
        elif f.file.corrupt:
            lines.append(
                f'head -c "$(stat -c%s {path})" /dev/urandom > /tmp/pg-corrupt && mv /tmp/pg-corrupt {path}'
            )
    lines.append("chmod +x /pg/shims/* 2>/dev/null || true")
    return "\n".join(lines) + "\n"


def _task_toml(s: Scenario, opts: CompileOptions) -> str:
    return (
        'schema_version = "1.4"\n\n'
        f"[task]\nname = {json.dumps('pg/' + s.id)}\n\n"
        f"[agent]\ntimeout_sec = {round(s.effective_timeout * opts.agent_timeout_factor)}\n\n"
        f"[verifier]\ntimeout_sec = {opts.verifier_timeout_sec}\n\n"
        "[environment]\n"
        f"build_timeout_sec = {opts.build_timeout_sec}\n"
        f"cpus = {opts.cpus}\n"
        f"memory_mb = {opts.memory_mb}\n"
        'network_mode = "allowlist"\n'
        f"allowed_hosts = {json.dumps(s.network.allow)}\n"
    )


def compile_task(
    scenario: Scenario,
    project_root: Path,
    snapshot: Path,
    out_dir: Path,
    opts: CompileOptions | None = None,
    seed: int = 0,
    agent: str = "claude-code",
    treatment: Treatment | None = None,
    arm: str = "without",
) -> Path:
    """Write a Harbor task for `scenario` to out_dir and return out_dir.

    A hook, MCP or instructions `treatment` is written into the repo copy when arm is "with"
    (see sandbox/treatments.py); an MCP install.sh is built into the image for both arms."""
    opts = opts or CompileOptions()
    if not scenario.check:
        raise ValueError(f"{scenario.id}: a task needs a check before it can be compiled")
    for f in scenario.faults:
        if f.http is not None:
            raise UnsupportedFaultError(
                f"{scenario.id}: http faults are not supported yet (planned for Plan 2b)"
            )
        if f.file is not None and f.file.unreadable:
            raise UnsupportedFaultError(
                f"{scenario.id}: 'unreadable' cannot be enforced because the agent runs as root"
            )
    if out_dir.exists():
        shutil.rmtree(out_dir)
    env = out_dir / "environment"
    repo = env / "repo"
    shutil.copytree(snapshot, repo)
    fixtures = project_root / PG_DIR / "fixtures" / scenario.id
    if fixtures.is_dir():
        shutil.copytree(fixtures, repo / "pg_fixtures", dirs_exist_ok=True)

    install = treatment_files.install_script(treatment)
    if treatment_files.is_config(treatment) and arm == "with":
        assert treatment is not None
        treatment_files.apply_with_arm(treatment, repo)

    if scenario.load is not None:
        if scenario.load.inputs is not None:
            generate_inputs(scenario.load.inputs.generate, scenario.load.inputs.count, repo, seed)
        if scenario.load.context_fill is not None:
            (repo / "PG_CONTEXT.md").write_text(context_fill_text(scenario.load.context_fill, seed))
            claude_md = repo / "CLAUDE.md"
            existing = claude_md.read_text() if claude_md.is_file() else ""
            claude_md.write_text(existing.rstrip("\n") + "\n\n@PG_CONTEXT.md\n")

    pg = env / "pg"
    (pg / "shims").mkdir(parents=True)
    (pg / "prepare.sh").write_text(_prepare_script(scenario))
    if install is not None:
        (pg / treatment_files.INSTALL_TARGET).write_text(install)
    by_cmd: dict[str, list[CommandFault]] = defaultdict(list)
    for f in scenario.faults:
        if f.command is not None:
            by_cmd[f.command.match.split()[0]].append(f.command)
    for cmd, faults in by_cmd.items():
        (pg / "shims" / cmd).write_text(_shim(cmd, faults))
    (env / "Dockerfile").write_text(
        base_dockerfile(project_root).rstrip("\n")
        + "\n"
        + install_snippet(agent)
        + DOCKERFILE_TAIL
        + (f"RUN bash /pg/{treatment_files.INSTALL_TARGET}\n" if install is not None else "")
    )

    tests = out_dir / "tests"
    tests.mkdir(parents=True)
    (tests / "test.sh").write_text(TEST_SH)
    (tests / "check.sh").write_text(f"#!/bin/bash\nset -eo pipefail\ncd /app\n{scenario.check}\n")
    checks = project_root / PG_DIR / "checks"
    if checks.is_dir():
        shutil.copytree(checks, tests / "checks")
    for script in (tests / "test.sh", tests / "check.sh"):
        script.chmod(0o755)

    (out_dir / "instruction.md").write_text(scenario.instruction.rstrip("\n") + "\n")
    (out_dir / "task.toml").write_text(_task_toml(scenario, opts))
    return out_dir
