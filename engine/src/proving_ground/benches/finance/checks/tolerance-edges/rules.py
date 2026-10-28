import csv
from pathlib import Path


def items(right: int, total: int) -> None:
    """Partial credit for Rig: how many invoices came out right (pass/fail is still the exit)."""
    print(f"RIG_ITEMS {right}/{total}", flush=True)


def decisions(rel: str) -> dict[str, tuple[str, str]]:
    f = Path("/app") / rel
    assert f.is_file(), f"no {rel}"
    rows = list(csv.DictReader(f.read_text().splitlines()))
    assert rows and {"invoice", "decision", "route"} <= set(rows[0]), (
        f"{rel}: header must be invoice,decision,route"
    )
    out = {}
    for r in rows:
        inv = (r["invoice"] or "").strip()
        assert inv not in out, f"{rel}: {inv} appears twice"
        out[inv] = ((r["decision"] or "").strip().lower(), (r["route"] or "").strip().lower())
    return out


def check(rel: str, expected: dict[str, tuple[str, str]]) -> None:
    # An invoice counts as right when its decision and route both match; a missing file, a bad
    # header, an unreadable file or a repeated invoice counts none right.
    try:
        got = decisions(rel)
    except Exception:
        items(0, len(expected))
        raise
    # Every invoice that shouldn't be there costs one, so only a passing file scores all.
    right = sum(got.get(k) == v for k, v in expected.items()) - len(set(got) - set(expected))
    items(max(0, right), len(expected))
    assert set(got) == set(expected), (
        f"{rel}: invoices {sorted(got)} but expected {sorted(expected)}"
    )
    wrong = [f"{k}: {got[k]} but the policy gives {v}" for k, v in expected.items() if got[k] != v]
    assert not wrong, "\n".join(wrong)
