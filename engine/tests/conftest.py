import copy
import threading
import time

import pytest

PLAN = {
    "workflow": {
        "id": "support",
        "name": "Support tickets",
        "success": "Every ticket gets the right outcome",
        "steps": [
            {"name": "triage", "type": "research", "why": "Read the ticket"},
            {"name": "fix", "type": "code", "why": "Change the code"},
        ],
    },
    "scenarios": [
        {
            "id": "refund-basic",
            "title": "Refund under the limit",
            "kind": "typical",
            "instruction": "Refund ticket T-1.",
            "check": "bash /tests/checks/refund-basic/check.sh",
            "step": "fix",
            "checks": [{"path": "check.sh", "content": "grep -q refunded out.txt\n"}],
        },
        {
            "id": "config-missing",
            "title": "Config file is gone",
            "kind": "failure",
            "instruction": "Start the service.",
            "check": "test -f REPORT.md",
            "faults": [{"file": {"path": "config.yaml", "remove": True}}],
        },
        {
            "id": "future-scale",
            "title": "Ten times the tickets",
            "kind": "imaginary",
            "instruction": "Triage the tickets in pg_fixtures/.",
            "check": "python3 /tests/checks/future-scale/check.py",
            "checks": [{"path": "check.py", "content": "raise SystemExit(1)\n"}],
            "fixtures": [{"path": "tickets.json", "content": "[]\n"}],
        },
    ],
    "treatments": [
        {"name": "tdd", "kind": "skill", "why": "Fixes need tests", "step": "fix"},
    ],
}
MIX_TEXT = "typical=1,failure=1,imaginary=1"


@pytest.fixture
def plan_data():
    """A valid generator output matching MIX_TEXT. Each test gets its own copy."""
    return copy.deepcopy(PLAN)


class _NoGitHub:
    """GitHub for tests that don't pass one: every call fails as if offline."""

    def search(self, query, sort, per_page):
        raise RuntimeError("no network in tests")

    def get(self, endpoint):
        raise RuntimeError("no network in tests")


@pytest.fixture(autouse=True)
def _no_skill_models(monkeypatch):
    """The skill matcher's models are never downloaded or loaded in tests (PG_SKILL_MODELS=off),
    and no app's matcher outlives its test; tests of the matcher turn it on with fakes."""
    from proving_ground import skill_models

    monkeypatch.setenv(skill_models.OFF, "off")
    yield
    skill_models.use(None)


@pytest.fixture(autouse=True)
def _offline_github(monkeypatch):
    """The Lab fetches its GitHub skills in the background; tests must never reach the network."""
    monkeypatch.setattr("proving_ground.api.app.default_github", lambda: _NoGitHub())


@pytest.fixture(autouse=True)
def _finish_background_work():
    """A run, suite or probe a test started in the background finishes before the next test
    swaps in its own fake agent; else its trials reach that fake and count as the next test's."""
    before = set(threading.enumerate())
    yield
    deadline = time.monotonic() + 5
    for t in set(threading.enumerate()) - before:
        t.join(timeout=max(0.0, deadline - time.monotonic()))
