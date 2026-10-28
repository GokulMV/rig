import sys

sys.path.insert(0, "/app")

cases = {
    "1h30m": 5400,
    "90s": 90,
    "2d": 172800,
    "45m": 2700,
    "1d2h3m4s": 93784,
    "30m1h": 5400,
    "1m1m": 120,
    "90": 90,
    "7h": 25200,
}
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


results = {text: run(text) for text in cases}
right = sum(err is None and got == cases[t] for t, (got, err) in results.items())
print(f"RIG_ITEMS {right}/{len(cases)}", flush=True)
for text, want in cases.items():
    got, err = results[text]
    if err is not None:
        raise err
    assert got == want, (text, got, want)
