"""Report 18: totals by month."""

from collections import defaultdict
from decimal import Decimal


def build_18(rows: list[dict]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(Decimal)
    for r in rows:
        out[r["key"]] += Decimal(r["amount"])
    return dict(out)
