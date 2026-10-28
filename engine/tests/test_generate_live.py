"""Paid: one real generator call, then a free no-agent preflight of every generated scenario.

`ANTHROPIC_API_KEY=... uv run pytest -m integration -s tests/test_generate_live.py`
Needs Docker too. One model call of up to 32k output tokens.
"""

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from proving_ground.generate.client import make_client
from proving_ground.generate.run import generate
from proving_ground.generate.schema import parse_mix
from proving_ground.intake import run_intake
from proving_ground.runner.harbor import HarborRunner
from proving_ground.sandbox.compiler import compile_task
from proving_ground.sandbox.snapshot import snapshot_repo
from proving_ground.store import Store

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY"),
]
MODEL = os.environ.get("PG_GENERATE_MODEL", "claude-sonnet-5-5")
MIX = "typical=2,edge=1,failure=1,overload=1,imaginary=1"
APP = '''\
"""Refund rules for the support desk."""

LIMITS = {"basic": 100, "pro": 1000}


def refund(plan: str, amount: int) -> str:
    """Return "approved", or "escalate" when the amount is over the plan's limit."""
    if amount > LIMITS[plan]:
        return "approved"
    return "escalate"
'''


def test_generated_scenarios_survive_preflight():
    d = Path.home() / ".cache" / "proving-ground-tests" / uuid.uuid4().hex[:8]
    try:
        proj = d / "proj"
        proj.mkdir(parents=True)
        (proj / "refunds.py").write_text(APP)
        (proj / "README.md").write_text(
            "Support desk tools. Refunds over the plan limit go to a manager.\n"
        )
        subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
        store = Store.for_project(proj)
        res = run_intake(store, proj)
        store.add_source(res.project_id, "usecase", "use-case", "Fix and extend refund rules.")
        out = generate(
            proj, store.list_sources(res.project_id), parse_mix(MIX), make_client(), MODEL
        )
        print("tokens", out.tokens_in, out.tokens_out)
        assert len(out.scenarios) == 6

        snap = snapshot_repo(proj, d / "snap")
        runner_tasks = {}
        for s in out.scenarios:
            s = s.model_copy(update={"check_status": "approved"})
            runner_tasks[s.id] = (s, compile_task(s, proj, snap.path, d / "tasks" / s.id))
        runner = HarborRunner({k: v[1] for k, v in runner_tasks.items()}, d / "trials", "unused")
        results = {k: runner.preflight(s, proj) for k, (s, _) in runner_tasks.items()}
        summary = {k: (r.setup_ok, r.check_passed_without_agent) for k, r in results.items()}
        print(summary)
        assert all(ok and not vacuous for ok, vacuous in summary.values()), {
            k: r.log for k, r in results.items()
        }
    finally:
        shutil.rmtree(d, ignore_errors=True)
