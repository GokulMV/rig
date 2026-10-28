import sys

sys.path.insert(0, "/app")

cases = {
    5400: "1h30m",
    90: "1m30s",
    172800: "2d",
    0: "0s",
    93784: "1d2h3m4s",
    3600: "1h",
    61: "1m1s",
    86401: "1d1s",
}
# Partial credit for Rig: one item per case and one for refusing a negative number, printed
# after the agent's code last runs so it has the last word. Pass/fail is still the asserts.
try:
    from durations import format_duration as f
except Exception:
    print(f"RIG_ITEMS 0/{len(cases) + 1}", flush=True)
    raise


def run(secs: int):
    try:
        return f(secs), None
    except Exception as e:
        return None, e


results = {secs: run(secs) for secs in cases}
_, negative = run(-1)
right = sum(err is None and got == cases[s] for s, (got, err) in results.items())
right += isinstance(negative, ValueError)
print(f"RIG_ITEMS {right}/{len(cases) + 1}", flush=True)
for secs, want in cases.items():
    got, err = results[secs]
    if err is not None:
        raise err
    assert got == want, (secs, got, want)
if negative is None:
    raise AssertionError("a negative number was accepted")
if not isinstance(negative, ValueError):
    raise negative
