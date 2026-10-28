import sys

sys.path.insert(0, "/tests/checks/hard-tables")
from rules import check  # noqa: E402

MONEY = ["per month", "a month", "monthly", "usd", "us dollars", "dollars", "in total", "total"]
PRICING_TEAM = "| Team | $19 | 10 | 1 |"
PRICING_BUSINESS = "| Business | $49 | 50 | 5 |"
PRICING_ENTERPRISE = "| Enterprise | Custom | Unlimited | 25 |"
INSIGHT = "| Insight (advanced reporting) | $8 | agent per month"
PACK = "| Extra contacts pack (50,000 contacts) | $30 | pack per month | Team, Business |"
SANDBOX = "| Sandbox workspace | $99 | sandbox per month ³ | Business, Enterprise |"
SAML = "SAML single sign-on is available on the Business plan and above"

check(
    {
        "HT1": {"value": 87, "units": MONEY, "evidence": [PRICING_TEAM, PACK]},
        "HT2": {
            "value": 205.8,
            "units": MONEY,
            "evidence": [
                "| Education | 30% | Team, Business, Enterprise | All |",
                PRICING_BUSINESS,
            ],
        },
        "HT3": {
            "value": 250000,
            "units": ["contacts"],
            "evidence": ["| Contacts per workspace | 10,000 | 100,000 | 1,000,000 |", PACK],
            "optional": ["Business and Enterprise limits are unchanged"],
        },
        "HT4": {
            "value": 30,
            "units": ["minutes"],
            "answers": ["half an hour", "0.5 hours"],
            "evidence": [
                "Every Enterprise workspace includes one sandbox at no charge",
                "the target is 30 minutes",
            ],
        },
        "HT5": {
            "value": 12,
            "units": ["hours"],
            "evidence": [
                SANDBOX,
                "Every Enterprise workspace includes one sandbox at no charge",
                "| Normal | 24 hours | 12 hours | 8 hours |",
            ],
            "optional": ["Every other cell of the table is correct"],
        },
        "HT6": {
            "value": 20,
            "units": ["tags"],
            "evidence": [SAML, "| Tags per ticket | 10 | 20 | 40 |"],
            "optional": [PRICING_BUSINESS],
        },
        "HT7": {
            "value": 15000,
            "units": ["contacts"],
            "evidence": ["Contacts per workspace on the Team plan rise to 25,000 (it was 10,000)"],
        },
        "HT8": {
            "value": 285,
            "units": MONEY,
            "evidence": [
                "| Nonprofit | 50% | Team, Business | Up to 20 |",
                "Agents beyond the number a programme covers pay the full plan price",
                PRICING_TEAM,
            ],
        },
        "HT9": {
            "value": 10,
            "units": ["agents", "seats"],
            "evidence": [
                "Insight is billed for every agent in the workspace, with a minimum of 10"
            ],
        },
        "HT10": {
            "value": 200,
            "units": MONEY,
            "evidence": [PRICING_ENTERPRISE, INSIGHT],
            "optional": ["Enterprise workspaces on annual billing get Insight at no charge"],
        },
        "HT11": {
            "value": 2000,
            "units": ["saved replies", "replies"],
            "evidence": [PRICING_ENTERPRISE, "| Saved replies | 100 | 500 | 2,000 |"],
        },
    },
    "out/hard-tables.json",
)
