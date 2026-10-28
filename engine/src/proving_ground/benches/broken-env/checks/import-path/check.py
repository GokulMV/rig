import sys

sys.path.insert(0, "/tests/checks/import-path")
from env import run, unchanged  # noqa: E402

out = run("scripts/test.sh")
assert "Ran 3 tests" in out, out[-500:]
unchanged()
