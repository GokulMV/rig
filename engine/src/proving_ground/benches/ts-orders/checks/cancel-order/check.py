import sys
from pathlib import Path

sys.path.insert(0, "/tests/checks/cancel-order")
from runner import run_tests  # noqa: E402

run_tests(Path("/tests/checks/cancel-order/hidden.test.ts"))
