import sys

sys.path.insert(0, "/tests/checks/tolerance-edges")
from rules import check  # noqa: E402

check(
    "out/edge.csv",
    {
        "INV-1101": ("approve", "none"),  # exactly 2% over: within tolerance
        "INV-1102": ("hold", "buyer"),  # 2.03% over
        "INV-1103": ("approve", "none"),  # exactly 2% under
        "INV-1104": ("hold", "receiving"),  # second line: 31 billed, 30 received
        "INV-1105": ("approve", "none"),
    },
)
