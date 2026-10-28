import sys

sys.path.insert(0, "/tests/checks/onboarding")
from rules import check  # noqa: E402

check(
    "out/decisions.csv",
    {
        "C-01": ("approve", "low"),
        "C-02": ("decline", "high"),  # sanctions: same name reordered, same date of birth
        "C-03": ("refer", "medium"),  # identity not verified
        "C-04": ("refer", "high"),  # PEP, accent ignored
        "C-05": ("refer", "high"),  # high-risk country
        "C-06": ("refer", "medium"),  # high volume, no source of funds
        "C-07": ("approve", "medium"),  # high volume with a source of funds
        "C-08": ("refer", "medium"),  # no proof of address
    },
)
