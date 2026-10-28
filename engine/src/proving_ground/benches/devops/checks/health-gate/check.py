import sys

sys.path.insert(0, "/tests/checks/health-gate")
from harness import run  # noqa: E402

code, out, calls = run(healthy_after=None)
assert code != 0, "an unhealthy deploy exited 0"
assert "rollback" in calls, "an unhealthy deploy wasn't rolled back"
assert calls.count("health") <= 3, "it checked health more than 3 times"
code, out, calls = run(healthy_after=2)
assert code == 0 and "rollback" not in calls, (
    "a deploy that became healthy on the 2nd try was rolled back"
)
