"""Generated layout in real containers, no model calls: `uv run pytest -m docker`."""

import shutil
import uuid
from pathlib import Path

import pytest

from proving_ground.generate.apply import write_plan
from proving_ground.generate.schema import parse_mix, parse_plan
from proving_ground.runner.harbor import HarborRunner
from proving_ground.sandbox.compiler import compile_task
from proving_ground.sandbox.snapshot import snapshot_repo

pytestmark = pytest.mark.docker

SEES_LAYOUT = """\
set -e
test -f /app/pg_fixtures/tickets.json
test ! -e /app/.proving-ground
test -x /tests/checks/future-scale/check.sh
"""


def test_generated_checks_and_fixtures_land_where_the_prompt_says(plan_data):
    # Docker VMs such as Colima only mount the home folder, so keep trial output under it.
    d = Path.home() / ".cache" / "proving-ground-tests" / uuid.uuid4().hex[:8]
    try:
        proj = d / "proj"
        proj.mkdir(parents=True)
        (proj / "app.py").write_text("print('hi')\n")
        imaginary = plan_data["scenarios"][2]
        imaginary["check"] = "bash /tests/checks/future-scale/check.sh"
        imaginary["checks"] = [{"path": "check.sh", "content": SEES_LAYOUT}]
        plan, scenarios = parse_plan(plan_data, parse_mix("typical=1,failure=1,imaginary=1"), set())
        write_plan(proj, plan, scenarios)
        s = next(x for x in scenarios if x.id == "future-scale")
        s = s.model_copy(update={"check_status": "approved"})
        snap = snapshot_repo(proj, d / "snap")
        task = compile_task(s, proj, snap.path, d / "tasks" / s.id)
        result = HarborRunner({s.id: task}, d / "trials", model="unused").preflight(s, proj)
        assert (result.setup_ok, result.check_passed_without_agent) == (True, True), result.log
    finally:
        shutil.rmtree(d, ignore_errors=True)
