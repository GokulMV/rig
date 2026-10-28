"""Real containers, no model calls: run with `uv run pytest -m docker`."""

import shutil
import uuid
from pathlib import Path

import pytest

from proving_ground.models import Scenario
from proving_ground.runner.harbor import HarborRunner
from proving_ground.sandbox.compiler import compile_task
from proving_ground.sandbox.snapshot import snapshot_repo

pytestmark = pytest.mark.docker

ADD_WORKS = 'python3 -c "import calc,sys; sys.exit(0 if calc.add(2,3)==5 else 1)"'


@pytest.fixture
def shared_dir():
    # Docker VMs such as Colima only mount the home folder, so keep trial output under it.
    d = Path.home() / ".cache" / "proving-ground-tests" / uuid.uuid4().hex[:8]
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def preflight_all(shared_dir: Path, scenarios: list[Scenario]):
    proj = shared_dir / "proj"
    proj.mkdir()
    (proj / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (proj / "config.yaml").write_text("env: prod\n")
    (proj / "data.csv").write_text("a,b\n1,2\n")
    snap = snapshot_repo(proj, shared_dir / "snap")
    tasks = {s.id: compile_task(s, proj, snap.path, shared_dir / "tasks" / s.id) for s in scenarios}
    runner = HarborRunner(tasks, shared_dir / "trials", model="unused")
    return {s.id: runner.preflight(s, proj) for s in scenarios}


def sc(sid: str, check: str, **kw) -> Scenario:
    return Scenario.model_validate(
        {"id": sid, "instruction": "x", "check": check, "check_status": "approved", **kw}
    )


def test_preflight_in_real_containers(shared_dir: Path):
    results = preflight_all(
        shared_dir,
        [
            sc("real-bug", ADD_WORKS),
            sc("vacuous", "true"),
            sc("bad-setup", "true", setup="exit 3"),
            sc(
                "faults",
                "bash -c 'git push; [ $? -eq 7 ]' && git --version && [ ! -e config.yaml ] && [ ! -s data.csv ]",
                kind="failure",
                faults=[
                    {"command": {"match": "git push", "exit": 7}},
                    {"file": {"path": "config.yaml", "remove": True}},
                    {"file": {"path": "data.csv", "truncate": True}},
                ],
            ),
            sc(
                "overload",
                "[ $(ls pg_inputs/tickets | wc -l) -eq 25 ] && grep -q '@PG_CONTEXT.md' CLAUDE.md "
                "&& [ $(wc -c < PG_CONTEXT.md) -gt 40000 ]",
                kind="overload",
                load={"inputs": {"generate": "tickets", "count": 25}, "context_fill": 10000},
            ),
            sc(
                "no-egress",
                "! python3 -c \"import urllib.request; urllib.request.urlopen('http://example.com', timeout=8)\"",
            ),
        ],
    )
    summary = {k: (v.setup_ok, v.check_passed_without_agent) for k, v in results.items()}
    assert summary == {
        "real-bug": (True, False),
        "vacuous": (True, True),
        "bad-setup": (False, False),
        "faults": (True, True),
        "overload": (True, True),
        "no-egress": (True, True),
    }, {k: v.log for k, v in results.items()}
