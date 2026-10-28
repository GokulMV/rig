import sys
from pathlib import Path

sys.path.insert(0, "/tests/checks/convert-rounding")
from runner import run_tests  # noqa: E402

run_tests(Path("/tests/checks/convert-rounding/hidden.test.ts"))
