import re
from pathlib import Path

f = Path("/app/out/recon.md")
try:
    text = f.read_text() if f.is_file() else ""
except Exception:
    text = ""


def line(label: str) -> str:
    m = re.findall(rf"^{label}:\s*(.+?)\s*$", text, re.M | re.I)
    assert m, f"missing the '{label}:' line"
    return m[-1]


def ids(v: str) -> list[str]:
    return (
        []
        if v.strip().lower() == "none"
        else sorted(x.strip().upper() for x in v.split(",") if x.strip())
    )


def amount(v: str) -> float:
    return float(v.replace("$", "").replace(",", ""))


# Partial credit for Rig: one item per closing line (unmatched bank, unmatched ledger,
# difference). Pass/fail is still the asserts below.
def _right(test) -> bool:
    try:
        return bool(test())
    except Exception:  # a missing line or a number that isn't one
        return False


right = sum(
    _right(t)
    for t in (
        lambda: ids(line("UNMATCHED BANK")) == ["B-05", "B-07", "B-08"],
        lambda: ids(line("UNMATCHED LEDGER")) == ["L-05", "L-07"],
        lambda: abs(amount(line("DIFFERENCE")) - 1019.12) < 0.005,
    )
)
print(f"RIG_ITEMS {right}/3", flush=True)

assert f.is_file(), "no out/recon.md"
assert ids(line("UNMATCHED BANK")) == ["B-05", "B-07", "B-08"], line("UNMATCHED BANK")
# B-07 and L-07 are 4 days apart: outside the 3-day window, so both stay unmatched.
assert ids(line("UNMATCHED LEDGER")) == ["L-05", "L-07"], line("UNMATCHED LEDGER")
diff = line("DIFFERENCE").replace("$", "").replace(",", "")
assert abs(float(diff) - 1019.12) < 0.005, diff
