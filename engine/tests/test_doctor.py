import subprocess
from pathlib import Path

from proving_ground.sandbox.doctor import run_checks


def fake(responses: dict[str, tuple[int, str]], on_mount=None):
    def run(cmd):
        key = " ".join(cmd[:2])
        if key == "docker run" and on_mount:
            on_mount(cmd)
        code, out = responses.get(key, (0, ""))
        return subprocess.CompletedProcess(cmd, code, out, "")

    return run


def test_all_good(tmp_path: Path):
    def write_probe(cmd):
        host = Path(cmd[cmd.index("-v") + 1].split(":")[0])
        (host / ".pg-probe").write_text("ok")

    run = fake({"docker info": (0, "29.5.2\n"), "docker compose": (0, "5.6.0\n")}, write_probe)
    checks = {c.name: c for c in run_checks(tmp_path / "runs", run, {"ANTHROPIC_API_KEY": "k"})}
    assert all(c.ok for c in checks.values()), checks
    assert checks["Docker"].detail == "server 29.5.2"
    assert not (tmp_path / "runs" / ".pg-probe").exists()


def test_unshared_folder_and_missing_key(tmp_path: Path):
    run = fake({"docker info": (0, "29\n"), "docker compose": (0, "5\n")})
    checks = {c.name: c for c in run_checks(tmp_path / "runs", run, {})}
    assert checks["Docker can see the runs folder"].ok is False
    assert "Colima" in checks["Docker can see the runs folder"].detail
    assert checks["Anthropic API key"].ok is False


def test_docker_missing(tmp_path: Path):
    def run(cmd):
        raise FileNotFoundError("docker")

    checks = {c.name: c for c in run_checks(tmp_path / "runs", run, {"ANTHROPIC_API_KEY": "k"})}
    assert checks["Docker"].ok is False
    assert "Docker Compose v2" not in checks
