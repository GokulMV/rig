"""Late Fee for APAC accounts."""

from decimal import Decimal

from ledger.util.rounding import to_minor

KIND = "late_fee"
REGION = "APAC"
PERCENT = Decimal("4.5")


def apply(amount: Decimal, currency: str = "EUR") -> Decimal:
    return to_minor(amount * PERCENT / 100, currency)
