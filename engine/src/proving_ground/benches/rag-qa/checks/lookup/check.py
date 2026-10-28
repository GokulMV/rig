import sys

sys.path.insert(0, "/tests/checks/lookup")
from rules import check  # noqa: E402

check(
    {
        "L1": {"answers": ["14 days", "14"], "evidence": ["free trial of 14 days"]},
        "L2": {
            "answers": ["10", "10 shared inboxes", "10 inboxes"],
            "evidence": ["up to 10 shared inboxes"],
        },
        "L3": {
            "answers": ["40", "40 rules", "40 active rules", "40 active automation rules"],
            "evidence": ["at most 40 active automation rules"],
        },
        "L4": {
            "answers": ["25 MB", "25MB", "25 megabytes"],
            "evidence": ["limited to 25 mb per file"],
        },
        "L5": {
            "answers": ["iOS 17", "17", "iOS 17 or later"],
            "evidence": ["requires ios 17 or later"],
        },
        "L6": {"answers": ["Marta Okafor"], "evidence": ["chief executive officer marta okafor"]},
    }
)
