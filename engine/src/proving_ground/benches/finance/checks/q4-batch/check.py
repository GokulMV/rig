import sys

sys.path.insert(0, "/tests/checks/q4-batch")
from rules import check  # noqa: E402

check(
    "out/q4.csv",
    {
        "INV-3001": ("approve", "none"),  # exactly 2% over
        "INV-3002": ("approve", "none"),
        "INV-3003": ("hold", "receiving"),  # 10 + 10 approved already, 15 more is over 30
        "INV-3004": ("approve", "none"),
        "INV-3005": ("approve", "none"),  # 90.78 vs 89.00: exactly 2% over
        "INV-3006": ("hold", "ap-lead"),  # resubmits INV-3002
    },
)
