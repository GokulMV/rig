"""Tax for EMEA accounts."""

from decimal import Decimal

from ledger.util.rounding import to_minor

KIND = "tax"
REGION = "EMEA"
PERCENT = Decimal("2")


def apply(amount: Decimal, currency: str = "EUR") -> Decimal:
    return to_minor(amount * PERCENT / 100, currency)
