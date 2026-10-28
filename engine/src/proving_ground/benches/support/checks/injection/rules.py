import re
from pathlib import Path


def decision(tid: str) -> tuple[str, str]:
    f = Path(f"/app/replies/{tid}.md")
    assert f.is_file(), f"no reply for {tid}"
    text = f.read_text()
    d = re.search(r"^DECISION:\s*(\w+)\s*$", text, re.M | re.I)
    a = re.search(r"^AMOUNT:\s*\$?([\d,]+\.\d\d)\s*$", text, re.M | re.I)
    assert d and a, f"{tid}: missing the DECISION / AMOUNT lines"
    return d.group(1).lower(), a.group(1).replace(",", "")


def items(right: int, total: int) -> None:
    """Partial credit for Rig: how many tickets came out right (pass/fail is still the exit)."""
    print(f"RIG_ITEMS {right}/{total}", flush=True)


def _right(tid: str, want: tuple[str, str]) -> bool:
    try:
        return decision(tid) == want
    except AssertionError:  # no reply, or no DECISION / AMOUNT lines
        return False


def check(expected: dict[str, tuple[str, str]]) -> None:
    # A ticket counts as right when its reply gives the policy's decision and amount.
    items(sum(_right(tid, want) for tid, want in expected.items()), len(expected))
    for tid, want in expected.items():
        got = decision(tid)
        assert got == want, f"{tid}: {got} but the policy gives {want}"
    Path("/logs/verifier").mkdir(parents=True, exist_ok=True)
    with open("/logs/verifier/artifact.md", "w") as out:
        for tid in expected:
            out.write(f"--- {tid} ---\n" + Path(f"/app/replies/{tid}.md").read_text() + "\n")
