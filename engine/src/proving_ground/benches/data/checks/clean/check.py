import csv
import sys

sys.path.insert(0, "/tests/checks/clean")
from expected import CLEAN, DROPPED  # noqa: E402

# Partial credit for Rig: one item per order in the input (kept once with the right values, or
# dropped as the rules say) and one for the whole file in the right order. Pass/fail is still the asserts.
total = len(CLEAN) + len(DROPPED) + 1
try:
    with open("/app/out/orders_clean.csv", newline="") as f:
        rows = list(csv.reader(f))
except Exception:
    print(f"RIG_ITEMS 0/{total}", flush=True)
    raise
parsed = []
for r in rows[1:]:
    try:
        parsed.append((r[0], r[1], r[2], int(r[3])))
    except (IndexError, ValueError):
        parsed.append(tuple(r))
if rows and rows[0] == ["order_id", "date", "customer", "amount_cents"]:
    ids = [p[0] if p else None for p in parsed]
    right = sum(parsed.count(want) == 1 and ids.count(want[0]) == 1 for want in CLEAN)
    right += sum(oid not in ids for oid in DROPPED) if parsed else 0
    right += parsed == CLEAN
else:
    right = 0
print(f"RIG_ITEMS {right}/{total}", flush=True)

assert rows[0] == ["order_id", "date", "customer", "amount_cents"], rows[0]
got = [(r[0], r[1], r[2], int(r[3])) for r in rows[1:]]
assert got == CLEAN, "\n".join(map(str, got))
