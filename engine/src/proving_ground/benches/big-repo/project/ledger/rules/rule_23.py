"""Late fee for APAC accounts (from the 2026 price list)."""

from decimal import Decimal

KIND = "late_fee"
REGION = "APAC"
PERCENT = Decimal("1.75")


def apply(amount: Decimal) -> Decimal:
    return amount * PERCENT / 100
