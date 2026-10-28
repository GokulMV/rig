"""Check that this machine can run sandboxed trials."""

from __future__ import annotations

import importlib.metadata
import os
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

Run = Callable[[list[str]], subprocess.CompletedProcess[str]]
PROBE_IMAGE = "busybox:1.36"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)


def run_checks(runs_dir: Path, run: Run = _run, env: Mapping[str, str] = os.environ) -> list[Check]:
    checks: list[Check] = []
    try:
        info = run(["docker", "info", "--format", "{{.ServerVersion}}"])
        docker_ok = info.returncode == 0
    except FileNotFoundError:
        info, docker_ok = None, False
    checks.append(
        Check(
            "Docker",
            docker_ok,
            f"server {info.stdout.strip()}"
            if docker_ok
            else "Docker is not running. Start Docker Desktop, Colima or OrbStack.",
        )
    )
    if docker_ok:
        compose = run(["docker", "compose", "version", "--short"])
        checks.append(
            Check(
                "Docker Compose v2",
                compose.returncode == 0,
                compose.stdout.strip()
                or "Install the Docker Compose v2 plugin (`docker compose`).",
            )
        )
        runs_dir.mkdir(parents=True, exist_ok=True)
        probe = runs_dir / ".pg-probe"
        probe.unlink(missing_ok=True)
        mount = run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{runs_dir.resolve()}:/pg",
                PROBE_IMAGE,
                "sh",
                "-c",
                "echo ok > /pg/.pg-probe",
            ]
        )
        shared = mount.returncode == 0 and probe.is_file()
        probe.unlink(missing_ok=True)
        checks.append(
            Check(
                "Docker can see the runs folder",
                shared,
                str(runs_dir)
                if shared
                else f"Docker cannot write to {runs_dir}. Colima and some VMs share only your "
                "home folder: keep the project under it, or add this path to the VM's mounts.",
            )
        )
    has_key = bool(env.get("ANTHROPIC_API_KEY") or env.get("ANTHROPIC_AUTH_TOKEN"))
    checks.append(
        Check(
            "Anthropic API key",
            has_key,
            "set" if has_key else "Set ANTHROPIC_API_KEY to run trials.",
        )
    )
    try:
        checks.append(Check("Harbor", True, importlib.metadata.version("harbor")))
    except importlib.metadata.PackageNotFoundError:
        checks.append(Check("Harbor", False, "harbor is not installed. Run `uv sync`."))
    return checks
