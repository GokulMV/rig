import sys

sys.path.insert(0, "/tests/checks/fail-fast")
from harness import run  # noqa: E402

code, out, calls = run(fail={"test"})
assert code != 0, "the release exited 0 although the tests failed"
assert "deploy" not in calls, "it deployed although the tests failed"
code, out, calls = run(fail={"build"})
assert code != 0 and "deploy" not in calls, "it deployed although the build failed"
code, out, calls = run()
assert code == 0 and "deploy" in calls, "a clean release no longer deploys"
