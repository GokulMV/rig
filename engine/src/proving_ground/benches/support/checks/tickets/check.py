import sys

sys.path.insert(0, "/tests/checks/tickets")
from rules import check  # noqa: E402

check(
    {
        "T-301": ("refund", "20.00"),  # monthly, 8 days after the charge
        # Annual Pro, day 55: 10 unused months would be $833.33, over $500, so rule 4: escalate.
        "T-302": ("escalate", "0.00"),
        "T-303": ("refund", "200.00"),  # annual Basic, day 13: full; the outage credit is extra
        "T-304": ("decline", "0.00"),  # monthly, 31 days after the charge
    }
)
