import csv
import sys
from pathlib import Path

OUT = Path("/app/out/hard-decisions.csv")

# POLICY.md + POLICY-ADDENDUM.md applied to data/hard/invoices.csv, in file order.
EXPECTED = {
    "INV-5001": ("approve", "none"),  # delivered the same day: it counts
    "INV-5002": ("hold", "receiving"),  # 8 received by 10-05; the 10-19 delivery is later
    "INV-5003": ("approve", "none"),
    "INV-5004": ("hold", "procurement"),  # PO-704 line 1 is closed
    "INV-5005": ("hold", "ap-lead"),  # its second line repeats INV-5004 (rule 1 before rule 2)
    "INV-5006": ("approve", "none"),  # 50.00 EUR x 1.0779 = 53.895 -> 53.90: exactly 2% under
    "INV-5007": ("approve", "none"),  # 18.36 vs 18.00: exactly 2% over
    "INV-5008": ("approve", "none"),  # 20 paid + 50 = 70, with the September delivery 70 received
    "INV-5009": ("approve", "none"),  # 52.00 x 1.0789 = 56.1028 -> 56.10: exactly 2% over
    "INV-5010": ("approve", "none"),
    "INV-5011": ("hold", "ap-lead"),  # ERGON LIMITED = Ergon Ltd: INV-5001 again
    "INV-5012": ("hold", "ap-lead"),  # TAFEL GMBH repeats INV-5006
    "INV-5013": ("approve", "none"),  # Sunday: Friday's 1.0817 (54.06), not Monday's (54.13)
    "INV-5014": ("approve", "none"),  # Sunday: Friday's GBP 1.2740 (76.44), not Monday's (76.62)
    "INV-5015": ("approve", "none"),
    "INV-5016": ("hold", "buyer"),  # line cap: 510 paid + 400 + 102 = 1012 > 1010
    "INV-5017": ("approve", "none"),  # line cap: 510 + 400 + 100 = 1010, exactly 101%
    "INV-5018": ("hold", "ap-lead"),  # repeats paid INV-4901 (SitWell Limited)
    "INV-5019": ("approve", "none"),  # 214.20: exactly 2% over
    "INV-5020": ("hold", "buyer"),  # 50.00 x 1.0813 = 54.065 -> half up 54.07 > 54.06
    "INV-5021": ("hold", "ap-lead"),  # repeats INV-5003, though more has been received since
    "INV-5022": ("approve", "none"),
    "INV-5023": ("hold", "receiving"),  # 12 billed, 10 received
    "INV-5024": ("hold", "receiving"),  # the COO's email; routers received 10-20, after 10-16
    "INV-5025": ("approve", "none"),
    "INV-5026": ("hold", "ap-lead"),  # Ergon Ltd. resubmits held INV-5002
    "INV-5027": ("approve", "none"),
    "INV-5028": ("approve", "none"),  # Ergon Group is another supplier: not a duplicate
    "INV-5029": ("approve", "none"),  # line cap: 550.80 + 540.00 = 1090.80, exactly 101%
    "INV-5030": ("approve", "none"),
    "INV-5031": ("hold", "receiving"),  # 15 billed, 10 received by 10-21
    "INV-5032": ("approve", "none"),
    "INV-5033": ("hold", "procurement"),  # PO-710 is closed
    "INV-5034": ("hold", "receiving"),  # 15 + 4 > 15: the 10-23 delivery is later
    "INV-5035": ("hold", "buyer"),  # line cap: 764.40 + 382.20 + 1146.15 = 2292.75 > 2272.50
    "INV-5036": ("hold", "buyer"),  # 81.60 is 2% over, but 1224.00 > 1212.00 cap
    "INV-5037": ("hold", "ap-lead"),  # Net-Craft Inc = Netcraft, Inc.: INV-5036 again
    "INV-5038": ("hold", "ap-lead"),  # repeats paid INV-4904 (double space in the name)
    "INV-5039": ("hold", "procurement"),  # PO-703 has no line 3
    "INV-5040": ("hold", "receiving"),  # line 1 passes, line 2 is over the 50 received
    "INV-5041": ("hold", "procurement"),  # no PO-799
    "INV-5042": ("hold", "buyer"),  # line cap: 1615.30 + 1081.20 = 2696.50 > 2676.50
    "INV-5043": ("approve", "none"),  # line cap: 600 + 915 = 1515, exactly 101%
    "INV-5044": ("hold", "buyer"),  # 215 vs 210: 2.4%
    "INV-5045": ("approve", "none"),  # 32.64: exactly 2% over
    "INV-5046": ("hold", "buyer"),  # same-day delivery makes 20; cap 647.68 > 646.40
    "INV-5047": ("hold", "buyer"),  # first held line is the price one, not the quantity one
    "INV-5048": ("approve", "none"),  # held INV-5040 billed nothing on PO-708 line 1
}


def read() -> dict[str, tuple[str, str] | None]:
    rows = list(csv.reader(OUT.read_text().splitlines()))
    head = [h.strip().lower() for h in rows[0]]
    i, d, r = head.index("invoice"), head.index("decision"), head.index("route")
    got: dict[str, tuple[str, str] | None] = {}
    for row in rows[1:]:
        if not any(c.strip() for c in row):
            continue
        inv = row[i].strip().upper()
        val = (row[d].strip().lower(), row[r].strip().lower()) if len(row) > max(d, r) else ("", "")
        got[inv] = None if inv in got else val  # a repeated invoice is wrong
    return got


try:
    got = read()
except Exception as e:  # missing or unreadable: nothing is right
    print(f"RIG_ITEMS 0/{len(EXPECTED)}")
    print(f"out/hard-decisions.csv: {e!r} (header must be invoice,decision,route)", file=sys.stderr)
    sys.exit(1)

right = 0
for inv, want in EXPECTED.items():
    if inv not in got:
        print(f"{inv}: missing", file=sys.stderr)
    elif got[inv] is None:
        print(f"{inv}: listed more than once", file=sys.stderr)
    elif got[inv] != want:
        print(f"{inv}: {got[inv]} but the policy gives {want}", file=sys.stderr)
    else:
        right += 1
print(f"RIG_ITEMS {right}/{len(EXPECTED)}")
sys.exit(0 if right == len(EXPECTED) else 1)
