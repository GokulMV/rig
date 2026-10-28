"""Processing fee for EUR invoices."""

from decimal import Decimal

from ledger.util.rounding import bankers

KIND = "fee"
REGION = "EMEA"
CURRENCY = "EUR"
PERCENT = Decimal("2.5")


def apply(amount: Decimal) -> Decimal:
    return bankers(amount * PERCENT / 100, CURRENCY)
