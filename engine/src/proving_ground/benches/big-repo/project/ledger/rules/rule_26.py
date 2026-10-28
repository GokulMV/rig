"""Tax for NA accounts."""

from decimal import Decimal

from ledger.util.rounding import to_minor

KIND = "tax"
REGION = "NA"
PERCENT = Decimal("3")


def apply(amount: Decimal, currency: str = "EUR") -> Decimal:
    return to_minor(amount * PERCENT / 100, currency)
