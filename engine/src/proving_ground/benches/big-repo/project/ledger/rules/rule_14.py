"""Tax for ANZ accounts."""

from decimal import Decimal

from ledger.util.rounding import to_minor

KIND = "tax"
REGION = "ANZ"
PERCENT = Decimal("1")


def apply(amount: Decimal, currency: str = "EUR") -> Decimal:
    return to_minor(amount * PERCENT / 100, currency)
