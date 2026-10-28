import csv
import sys
from pathlib import Path


def check(rel: str, expected: dict[str, tuple[str, str]]) -> None:
    """Print RIG_ITEMS right/total, list each wrong customer on stderr, exit 0 only if all right."""
    wrong: list[str] = []
    broken = False
    try:
        text = (Path("/app") / rel).read_text(encoding="utf-8-sig")
        rows = list(csv.reader(text.splitlines()))
        head = [h.strip().lower() for h in rows[0]]
        ci, di, ri = head.index("customer"), head.index("decision"), head.index("risk")
        got: dict[str, list[tuple[str, str]]] = {}
        for r in rows[1:]:
            if len(r) > max(ci, di, ri):
                got.setdefault(r[ci].strip().upper(), []).append(
                    (r[di].strip().lower(), r[ri].strip().lower())
                )
        for cid, want in expected.items():
            seen = got.get(cid, [])
            if len(seen) != 1:
                wrong.append(f"{cid}: {len(seen)} rows, expected one")
            elif seen[0] != want:
                wrong.append(f"{cid}: {','.join(seen[0])} but the policy gives {','.join(want)}")
    except Exception as e:  # missing or unreadable file: nothing is right
        print(f"{rel}: cannot read it as CSV with customer,decision,risk: {e}", file=sys.stderr)
        broken = True
    right = 0 if broken else len(expected) - len(wrong)
    print(f"RIG_ITEMS {right}/{len(expected)}")
    if wrong:
        print("\n".join(wrong), file=sys.stderr)
    if broken or wrong:
        sys.exit(1)
