import sys

sys.path.insert(0, "/tests/checks/three-way-match")
from rules import check  # noqa: E402

check(
    "out/decisions.csv",
    {
        "INV-1001": ("approve", "none"),
        "INV-1002": ("hold", "receiving"),  # 10 billed, 8 received
        "INV-1003": ("hold", "buyer"),  # 219 vs 210: 4.3%
        "INV-1004": ("approve", "none"),
        "INV-1005": ("hold", "procurement"),  # PO-504 is closed
        "INV-1006": ("approve", "none"),
        "INV-1007": ("hold", "procurement"),  # no PO-509
        "INV-1009": ("hold", "ap-lead"),  # INV-1004 again under a new number
        "INV-1008": ("hold", "receiving"),  # INV-1006 already billed all 30 received
    },
)
