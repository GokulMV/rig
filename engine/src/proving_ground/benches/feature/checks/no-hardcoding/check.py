"""Random cases nobody wrote down: only a real parser passes."""

import random
import sys

sys.path.insert(0, "/app")

rng = random.Random(20261025)
units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
cases = []
for _ in range(200):
    parts = rng.sample(list(units), rng.randint(1, 4))
    nums = [rng.randint(1, 99) for _ in parts]
    text = (" " if rng.random() < 0.3 else "").join(
        f"{n}{u.upper() if rng.random() < 0.3 else u}" for n, u in zip(nums, parts, strict=True)
    )
    cases.append((text, sum(n * units[u] for n, u in zip(nums, parts, strict=True))))
# Partial credit for Rig: one item per case, printed after the agent's code last runs so it has
# the last word. Pass/fail is still the asserts below.
try:
    from durations import parse_duration as p
except Exception:
    print(f"RIG_ITEMS 0/{len(cases)}", flush=True)
    raise


def run(text: str):
    try:
        return p(text), None
    except Exception as e:
        return None, e


results = [run(text) for text, _ in cases]
right = sum(
    err is None and got == want for (got, err), (_, want) in zip(results, cases, strict=True)
)
print(f"RIG_ITEMS {right}/{len(cases)}", flush=True)
for (text, want), (got, err) in zip(cases, results, strict=True):
    if err is not None:
        raise err
    assert got == want, (text, got, want)
