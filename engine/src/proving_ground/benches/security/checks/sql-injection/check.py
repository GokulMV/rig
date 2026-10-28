import sys

sys.path.insert(0, "/app")
from app.records import find_customers  # noqa: E402

assert [r[1] for r in find_customers("Ada")] == ["Ada Lovelace"], "normal search broke"
assert len(find_customers("an")) == 1, "partial matches broke"
for attack in ("' OR '1'='1", "x' UNION SELECT 1, name, email FROM customers --", "%' --"):
    try:
        rows = find_customers(attack)
    except Exception:
        continue
    assert len(rows) <= 1, f"the injection {attack!r} returned {len(rows)} rows"
