"""Discount for APAC accounts."""

from decimal import Decimal

from ledger.util.rounding import to_minor

KIND = "discount"
REGION = "APAC"
PERCENT = Decimal("1.25")


def apply(amount: Decimal, currency: str = "EUR") -> Decimal:
    return to_minor(amount * PERCENT / 100, currency)
