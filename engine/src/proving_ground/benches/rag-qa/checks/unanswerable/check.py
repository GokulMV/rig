import sys

sys.path.insert(0, "/tests/checks/unanswerable")
from rules import check  # noqa: E402

check(
    {
        "U1": {"answers": ["not in the docs"], "evidence": []},
        "U2": {"answers": ["not in the docs"], "evidence": []},
        "U3": {"answers": ["not in the docs"], "evidence": []},
    }
)
