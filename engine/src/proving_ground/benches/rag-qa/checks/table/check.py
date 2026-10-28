import sys

sys.path.insert(0, "/tests/checks/table")
from rules import check  # noqa: E402

check(
    {
        "T1": {"answers": ["25", "25 agents"], "evidence": ["enterprise custom unlimited 25"]},
        "T2": {
            "answers": ["4 hours", "4", "4h", "4 hrs"],
            "evidence": ["high 8 hours 4 hours 2 hours"],
        },
        "T3": {
            "answers": ["20", "20 custom fields", "20 fields"],
            "evidence": ["custom fields per ticket 20 50 100"],
        },
    }
)
