import sys

sys.path.insert(0, "/tests/checks/held-out-batch")
from rules import check  # noqa: E402

check(
    {
        "H1": {
            "answers": ["4.4", "version 4.4", "v4.4"],
            "evidence": ["version 4.4 adds audit log export"],
        },
        "H2": {"answers": ["5", "5 agents"], "evidence": ["business 49 50 5"]},
        "H3": {
            "answers": ["99.95%", "99.95", "99.95 percent"],
            "evidence": [
                "enterprise custom unlimited 25",
                "enterprise plans carry a 99.95 uptime commitment",
            ],
        },
        "H4": {"answers": ["not in the docs"], "evidence": []},
    }
)
