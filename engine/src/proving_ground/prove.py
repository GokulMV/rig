"""Prove a generated check: run it on the untouched repo with no agent, no model, $0."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from proving_ground.files import PG_DIR
from proving_ground.models import Scenario
from proving_ground.runner.harbor import HarborRunner
from proving_ground.sandbox.compiler import compile_task
from proving_ground.sandbox.snapshot import snapshot_repo


@dataclass(frozen=True)
class Proof:
    proven: bool | None  # True: failed untouched (good). False: passed untouched (broken).
    detail: str = ""


def prove_scenario(scenario: Scenario, root: Path) -> Proof:
    """Snapshot the repo, compile this one scenario, run its check with no agent."""
    out = root / PG_DIR / "prove" / scenario.id
    snap = snapshot_repo(root, out / "snapshot")
    task = compile_task(scenario, root, snap.path, out / "task")
    runner = HarborRunner({scenario.id: task}, out / "trials", model=None, agent="nop")
    pre = runner.preflight(scenario, root)
    if not pre.setup_ok:
        return Proof(None, pre.log or "the sandbox could not be built")
    if pre.check_passed_without_agent:
        return Proof(False, "The check passes on the untouched repo, so it proves nothing.")
    return Proof(True, "The check fails on the untouched repo, as it should.")


class ProveJobs:
    """Background prove runs, keyed by repo id and scenario id. Docker builds take minutes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[tuple[str, str], dict] = {}

    def start(self, key: tuple[str, str], work: Callable[[], Proof]) -> bool:
        """Start a run; False if one is already running for this key."""
        with self._lock:
            if self._jobs.get(key, {}).get("status") == "running":
                return False
            self._jobs[key] = {"status": "running", "proven": None, "detail": ""}

        def run() -> None:
            try:
                p = work()
                res = {
                    "status": "error" if p.proven is None else "done",
                    "proven": p.proven,
                    "detail": p.detail,
                }
            except Exception as e:  # noqa: BLE001 - any failure is shown, never crashes the thread
                res = {"status": "error", "proven": None, "detail": str(e) or type(e).__name__}
            with self._lock:
                self._jobs[key] = res

        threading.Thread(target=run, daemon=True).start()
        return True

    def get(self, key: tuple[str, str]) -> dict:
        with self._lock:
            return dict(self._jobs.get(key, {"status": "idle", "proven": None, "detail": ""}))
