"""Report 3: totals by region."""

from collections import defaultdict
from decimal import Decimal


def build_3(rows: list[dict]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(Decimal)
    for r in rows:
        out[r["key"]] += Decimal(r["amount"])
    return dict(out)
