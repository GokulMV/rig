import sys

sys.path.insert(0, "/tests/checks/multi-hop")
from rules import check  # noqa: E402

check(
    {
        "M1": {
            "answers": ["$49", "49", "49 per agent per month", "$49 per agent per month"],
            "evidence": ["saml single sign-on is available on the business plan", "business 49"],
        },
        "M2": {
            "answers": ["$12", "12", "12 per workspace per month", "$12 per workspace per month"],
            "evidence": [
                "turn on the polyglot add-on",
                "polyglot costs 12 per workspace per month",
            ],
        },
        "M3": {
            "answers": ["Nordhost"],
            "evidence": [
                "customers billed in euros are placed in the eu data region",
                "nordhost hosts the eu data region",
            ],
        },
        "M4": {
            "answers": ["Dev Ramanathan"],
            "evidence": ["escalations go to the head of support", "head of support dev ramanathan"],
        },
    }
)
