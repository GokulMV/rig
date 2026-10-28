import sys

sys.path.insert(0, "/tests/checks/fuzzy-names")
from rules import check  # noqa: E402

check(
    "out/fuzzy.csv",
    {
        "C-09": ("decline", "high"),  # accents, hyphen and order differ; same person
        "C-10": ("refer", "high"),  # same name, different date of birth: possible match
        "C-11": ("approve", "low"),  # initials are not a match
    },
)
