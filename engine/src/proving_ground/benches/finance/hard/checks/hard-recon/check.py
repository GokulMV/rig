import re
import sys
from pathlib import Path

OUT = Path("/app/out/hard-recon.md")

BANK = [f"B-{i}" for i in range(101, 143)]
LEDGER = [f"L-{i}" for i in range(201, 244)]

# Bank lines in date order, each taking the earliest unmatched ledger line with the same amount
# within 3 days (POLICY.md, spelled out in POLICY-ADDENDUM.md).
UNMATCHED_BANK = {
    "B-106",  # -312.40, ledger 10-02 vs bank 10-06: 4 days
    "B-114",  # bank fee, not in the ledger
    "B-115",  # courier -95.00: B-111 took L-207 (earliest), L-212 is 4 days off
    "B-116",  # Fabrikam 420.00: value-dated B-141 (10-13, last in the file) goes first
    "B-120",  # second -18.99 licence the same day; one in the ledger
    "B-125",  # returned payment +310.00: never paired with the payment it returns
    "B-127",  # +75.00 refund; the ledger has -75.00
    "B-129",  # Northwind 1150.00: ledger 10-31 is 4 days later
    "B-132",  # Ergon -1312.00: ledger 10-24 is 5 days earlier, whatever the close note says
    "B-134",  # interest
    "B-139",  # -1206.00 vs ledger -1260.00: transposed digits
    "B-142",  # correction -12.18; ledger 11-02 is 21 days later
}
UNMATCHED_LEDGER = {
    "L-202",  # Cloudly 09-29: B-104 (10-05) is 6 days off, so B-104 takes L-208 and B-108 L-211
    "L-205",  # -312.40, 4 days
    "L-212",  # courier 10-11: B-111 took the earlier L-207
    "L-216",  # -640.00 and its reversal: neither is on the bank
    "L-217",
    "L-226",  # insurance posted twice; the first (file order) matches B-126
    "L-228",  # Ergon -1312.00, 5 days
    "L-229",  # ACME 10-25: B-137 (10-31) is 6 days off and takes L-233
    "L-230",  # -75.00 vs +75.00
    "L-237",  # -1260.00 vs -1206.00
    "L-239",  # Lumen deposit, not yet on the bank
    "L-240",  # Northwind, 4 days
    "L-243",  # correction, 21 days
}
DIFFERENCE = "-213.62"  # every bank line minus every ledger line; never plugged to 0.00

TOTAL = len(BANK) + len(LEDGER) + 1


def line(text: str, label: str) -> str:
    m = re.findall(rf"^\W*{label}\W*:\s*(.+?)\s*$", text, re.M | re.I)
    assert m, f"missing the '{label}:' line"
    return m[-1]


def ids(v: str) -> set[str]:
    v = v.strip().strip("`*").strip()
    return set() if v.lower() == "none" else {x.strip().upper() for x in v.split(",") if x.strip()}


try:
    text = OUT.read_text()
    bank = ids(line(text, "UNMATCHED BANK"))
    ledger = ids(line(text, "UNMATCHED LEDGER"))
    diff_text = line(text, "DIFFERENCE").replace("$", "").replace(",", "").strip("`* ")
except Exception as e:  # missing or unreadable: nothing is right
    print(f"RIG_ITEMS 0/{TOTAL}")
    print(f"out/hard-recon.md: {e}", file=sys.stderr)
    sys.exit(1)

right = 0
for side, every, want, got in (
    ("bank", BANK, UNMATCHED_BANK, bank),
    ("ledger", LEDGER, UNMATCHED_LEDGER, ledger),
):
    for i in every:
        if (i in want) == (i in got):
            right += 1
        else:
            print(
                f"{i}: listed as unmatched but it matches"
                if i in got
                else f"{i}: unmatched but not listed under UNMATCHED {side.upper()}",
                file=sys.stderr,
            )
try:
    ok = abs(float(diff_text) - float(DIFFERENCE)) < 0.005
except ValueError:
    ok = False
if ok:
    right += 1
else:
    print(f"DIFFERENCE: {diff_text} but bank minus ledger is {DIFFERENCE}", file=sys.stderr)
print(f"RIG_ITEMS {right}/{TOTAL}")
sys.exit(0 if right == TOTAL else 1)
