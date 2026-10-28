import sys

sys.path.insert(0, "/tests/checks/prd")
from rules import check  # noqa: E402

check()
