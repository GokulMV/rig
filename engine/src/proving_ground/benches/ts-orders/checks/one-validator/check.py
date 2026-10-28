import sys
from pathlib import Path

sys.path.insert(0, "/tests/checks/one-validator")
from runner import run_tests  # noqa: E402

run_tests(Path("/tests/checks/one-validator/hidden.test.ts"))

# One validator, in src/sku.ts, used by both.
import re  # noqa: E402

src = Path("/app/src")
defs = [
    p.name
    for p in src.glob("*.ts")
    for _ in re.finditer(r"(function\s+validateSku\b|validateSku\s*=)", p.read_text())
]
assert defs == ["sku.ts"], (
    f"validateSku is defined in {defs or 'no file'}; it should be defined once, in src/sku.ts"
)
for m in ("inventory.ts", "orders.ts"):
    assert re.search(r"from\s+[\"']\./sku(\.ts)?[\"']", (src / m).read_text()), (
        f"{m} doesn't use src/sku.ts"
    )
