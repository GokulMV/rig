import sys

sys.path.insert(0, "/tests/checks/conflicting")
from rules import check  # noqa: E402

check(
    {
        "C1": {"answers": ["30 days", "30"], "evidence": ["refunded within 30 days of purchase"]},
        "C2": {"answers": ["90 days", "90"], "evidence": ["purged 90 days after deletion"]},
        "C3": {
            "answers": ["600", "600 requests per minute", "600 requests"],
            "evidence": ["600 requests per minute"],
        },
    }
)
