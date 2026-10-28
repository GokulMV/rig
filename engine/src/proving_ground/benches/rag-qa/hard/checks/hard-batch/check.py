import sys

sys.path.insert(0, "/tests/checks/hard-batch")
from rules import NOT_IN_DOCS, check  # noqa: E402

MONEY = ["per month", "a month", "monthly", "usd", "us dollars", "dollars", "in total", "total"]
NONE = {"answers": [NOT_IN_DOCS], "evidence": []}
PRICING_BUSINESS = "| Business | $49 | 50 | 5 |"
INSIGHT = "| Insight (advanced reporting) | $8 | agent per month"
NONPROFIT = "| Nonprofit | 50% | Team, Business | Up to 20 |"

check(
    {
        "HB1": {
            "value": 25000,
            "units": ["contacts"],
            "evidence": ["Contacts per workspace on the Team plan rise to 25,000"],
        },
        "HB2": {
            "value": 100000,
            "units": ["contacts"],
            "evidence": ["| Contacts per workspace | 10,000 | 100,000 | 1,000,000 |"],
            "optional": ["Business and Enterprise limits are unchanged"],
        },
        "HB3": {
            "value": 125000,
            "units": ["contacts"],
            "evidence": [
                "Contacts per workspace on the Team plan rise to 25,000",
                "| Extra contacts pack (50,000 contacts) | $30 | pack per month | Team, Business |",
            ],
        },
        "HB4": {
            "value": 80,
            "units": MONEY,
            "evidence": [
                PRICING_BUSINESS,
                INSIGHT,
                "Insight is billed for every agent in the workspace, with a minimum of 10 agents",
            ],
        },
        "HB5": {"value": 240, "units": MONEY, "evidence": [INSIGHT]},
        "HB6": {
            "value": 0,
            "units": MONEY,
            "answers": ["free", "nothing", "no charge", "at no charge", "included"],
            "evidence": ["Enterprise workspaces on annual billing get Insight at no charge"],
        },
        "HB7": {
            "value": 297,
            "units": MONEY,
            "evidence": [
                "Every Enterprise workspace includes one sandbox at no charge; "
                "each further sandbox is $99 per month"
            ],
        },
        "HB8": {
            "value": 198,
            "units": MONEY,
            "evidence": ["| Sandbox workspace | $99 | sandbox per month"],
        },
        "HB9": {
            "value": 30,
            "units": ["days", "every"],
            "evidence": ["Sandbox data is reset every 30 days"],
        },
        "HB10": {"value": 8, "units": ["times"], "evidence": ["retried up to 8 times"]},
        "HB11": {
            "value": 48,
            "units": ["hours"],
            "evidence": ["the retry window of 48 hours"],
            "optional": ["a retry window of 48 hours"],
        },
        "HB12": {
            "value": 50,
            "units": ["versions"],
            "evidence": ["now keeps its last 50 versions"],
        },
        "HB13": {
            "value": 5,
            "units": ["minutes", "every"],
            "evidence": ["refresh every 5 minutes on the Business and Enterprise plans"],
        },
        "HB14": {
            "value": 15,
            "units": ["minutes", "every"],
            "evidence": ["refresh every 15 minutes"],
        },
        "HB15": {
            "value": 30,
            "units": ["minutes"],
            "answers": ["half an hour", "0.5 hours"],
            "evidence": ["the target is 30 minutes"],
        },
        "HB16": {
            "value": 2,
            "units": ["hours"],
            "evidence": [
                "SCIM is available on Enterprise only",
                "| High | 8 hours | 4 hours | 2 hours |",
            ],
            "optional": ["Every other cell of the table is correct"],
        },
        "HB17": {"answers": ["York"], "evidence": ["is headquartered in York"]},
        "HB18": {
            "answers": ["Cloudvale"],
            "evidence": [
                "all others are placed in the US data region",
                "Cloudvale hosts the US data region",
            ],
        },
        "HB19": {"value": 14, "units": ["languages"], "evidence": ["supports 14 languages"]},
        "HB20": {
            "value": 50,
            "units": ["percent", "off", "discount"],
            "answers": ["half"],
            "evidence": [NONPROFIT],
        },
        "HB21": {
            "value": 686,
            "units": MONEY,
            "evidence": [
                NONPROFIT,
                "Agents beyond the number a programme covers pay the full plan price",
                PRICING_BUSINESS,
            ],
        },
        "HB22": {
            "value": 96,
            "units": MONEY,
            "evidence": ["Discounts apply to the plan price only, never to add-ons", INSIGHT],
        },
        "HB23": {
            "value": 12,
            "units": ["months"],
            "evidence": ["The startup discount lasts for the first 12 months"],
        },
        "HB24": {
            "value": 237.5,
            "units": MONEY,
            "evidence": [
                "| Startup | 25% ¹ | Team, Business | Up to 10 |",
                "Agents beyond the number a programme covers pay the full plan price",
                "| Team | $19 | 10 | 1 |",
            ],
        },
        "HB25": NONE,
        "HB26": NONE,
        "HB27": NONE,
        "HB28": NONE,
        "HB29": NONE,
        "HB30": {
            "value": 8,
            "units": MONEY + ["per agent per month", "per agent", "an agent"],
            "evidence": [INSIGHT],
        },
        "HB31": {
            "value": 60,
            "units": ["months"],
            "evidence": ["report data is kept for 60 months instead of 24"],
        },
        "HB32": {
            "value": 500,
            "units": ["saved replies", "replies"],
            "evidence": ["| Saved replies | 100 | 500 | 2,000 |"],
        },
        "HB33": {
            "value": 20,
            "units": ["tags"],
            "evidence": ["| Tags per ticket | 10 | 20 | 40 |"],
        },
        "HB34": {
            "value": 65,
            "units": ["days"],
            "evidence": [
                "all its data is purged 30 days after closure. "
                "Backups roll off within a further 35 days"
            ],
        },
        "HB35": {
            "value": 2,
            "units": ["hours"],
            "evidence": ["| Urgent | 4 hours | 2 hours | 1 hour |"],
            "optional": ["Every other cell of the table is correct"],
        },
        "HB36": {"value": 245, "units": MONEY, "evidence": [PRICING_BUSINESS]},
        "HB37": NONE,
    },
    "out/hard-answers.json",
)
