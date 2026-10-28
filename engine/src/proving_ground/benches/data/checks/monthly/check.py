import json
import sys

sys.path.insert(0, "/tests/checks/monthly")
from expected import MONTHLY  # noqa: E402

# Partial credit for Rig: one item per month, right when its revenue matches; any month that
# shouldn't be there costs one. Pass/fail is still the assert.
try:
    got = json.load(open("/app/out/monthly.json"))
except Exception:
    print(f"RIG_ITEMS 0/{len(MONTHLY)}", flush=True)
    raise
if isinstance(got, dict):
    right = sum(got.get(k) == v for k, v in MONTHLY.items()) - len(set(got) - set(MONTHLY))
else:
    right = 0
print(f"RIG_ITEMS {max(0, right)}/{len(MONTHLY)}", flush=True)
assert got == MONTHLY, got
