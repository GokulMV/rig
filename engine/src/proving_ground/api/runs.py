"""Run one experiment at a time in a background thread and fan its events out."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator

from proving_ground.api.views import summary_json
from proving_ground.runner.harbor import AgentAuthError
from proving_ground.scheduler import NotRunnableError, PreflightError
from proving_ground.service import PreparedExperiment, execute

KEEPALIVE_S = 15.0


class Run:
    def __init__(self, eid: int):
        self.eid = eid
        self.events: list[dict] = []
        self.done = False
        self._cond = threading.Condition()

    def push(self, event: dict) -> None:
        with self._cond:
            self.events.append(event)
            self._cond.notify_all()

    def finish(self, event: dict) -> None:
        with self._cond:
            self.events.append(event)
            self.done = True
            self._cond.notify_all()

    def follow(self, keepalive_s: float = KEEPALIVE_S) -> Iterator[dict | None]:
        """Yield every event from the first; None means "nothing new, keep the line open"."""
        i = 0
        while True:
            with self._cond:
                if i >= len(self.events) and not self.done:
                    self._cond.wait(keepalive_s)
                batch, finished = self.events[i:], self.done
            i += len(batch)
            if not batch and not finished:
                yield None
            yield from batch
            if finished:  # finish() appends its event before setting done, so batch held it
                return


class RunManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.runs: dict[int | str, Run] = {}  # by experiment id, or "lab:<bench>:<id>" for a bench
        self.active: Run | None = None
        self.prepared: dict[int | str, PreparedExperiment] = {}

    def current(self) -> tuple[int | str, PreparedExperiment] | None:
        """The run going now, by its key, with what it runs; None when nothing is going."""
        with self._lock:
            if not self.active or self.active.done:
                return None
            key = next((k for k, r in self.runs.items() if r is self.active), None)
            p = self.prepared.get(key) if key is not None else None
            return (key, p) if p is not None else None

    def busy(self) -> int | None:
        with self._lock:
            return self.active.eid if self.active and not self.active.done else None

    def start(
        self,
        prepared: PreparedExperiment,
        key: int | str | None = None,
        after: Callable[[], None] | None = None,
    ) -> Run:
        run = Run(prepared.eid)
        with self._lock:
            self.runs[prepared.eid if key is None else key] = run
            self.prepared[prepared.eid if key is None else key] = prepared
            self.active = run
        threading.Thread(target=self._work, args=(prepared, run, after), daemon=True).start()
        return run

    def stop(self, key: int | str) -> bool:
        """Stop the run after the trial in progress. False when there's no such run going."""
        with self._lock:
            run = self.runs.get(key)
            p = self.prepared.get(key)
        if run is None or run.done or p is None:
            return False
        p.stop.set()
        return True

    def _work(
        self, p: PreparedExperiment, run: Run, after: Callable[[], None] | None = None
    ) -> None:
        try:
            summary = execute(p, run.push)
        except (NotRunnableError, PreflightError) as e:
            last = {"type": "error", "detail": str(e)}
        except AgentAuthError as e:
            last = {
                "type": "error",
                "detail": f"Claude Code could not sign in. Check the key. ({e})",
            }
        except Exception as e:  # noqa: BLE001 - report anything else to the page, not a dead thread
            last = {"type": "error", "detail": f"The run stopped: {type(e).__name__}: {e}"}
        else:
            status = p.store.get_experiment(p.eid).status
            last = {"type": "finished", "status": status, "summary": summary_json(summary)}
        # Before finish(): anyone who sees the run is done also finds what it wrote.
        if after is not None:
            after()
        run.finish(last)


def sse(events: Iterator[dict | None]) -> Iterator[str]:
    for e in events:
        yield ": keepalive\n\n" if e is None else f"data: {json.dumps(e)}\n\n"
