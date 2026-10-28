import sys

sys.path.insert(0, "/app")

GOOD = {"1h 30m": 5400, "  2H ": 7200, "1D 1M": 86460}
BAD = ("", "h", "5y", "-5m", "1.5h", "1h x", "   ", "m30")
# Partial credit for Rig: one item per input, good or bad, printed after the agent's code last
# runs so it has the last word. Pass/fail is still the asserts below.
try:
    from durations import parse_duration as p
except Exception:
    print(f"RIG_ITEMS 0/{len(GOOD) + len(BAD)}", flush=True)
    raise


def run(text: str):
    try:
        return p(text), None
    except Exception as e:
        return None, e


results = {text: run(text) for text in (*GOOD, *BAD)}
right = sum(results[t][1] is None and results[t][0] == w for t, w in GOOD.items())
right += sum(isinstance(results[t][1], ValueError) for t in BAD)
print(f"RIG_ITEMS {right}/{len(GOOD) + len(BAD)}", flush=True)
for text, want in GOOD.items():
    got, err = results[text]
    if err is not None:
        raise err
    assert got == want
for bad in BAD:
    got, err = results[bad]
    if isinstance(err, ValueError):
        continue
    if err is not None:
        raise err
    raise AssertionError(f"{bad!r} was accepted as {got}")
