import sys

sys.path.insert(0, "/tests/checks/second-batch")
from rules import check  # noqa: E402

check(
    "out/second.csv",
    {
        "C-13": ("refer", "high"),  # PEP: case and order differ
        "C-14": ("approve", "low"),  # an extra family name is not the listed person
        "C-15": ("approve", "low"),  # 50,000 is not over 50,000
    },
)
