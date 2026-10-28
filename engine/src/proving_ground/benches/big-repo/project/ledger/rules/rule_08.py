"""DEPRECATED: the 2024 APAC late fee. Replaced by rule_23; kept for old reports only.
Not loaded by invoices (see ledger/reports/invoice.py)."""

from decimal import Decimal

KIND = "late_fee_2024"
REGION = "APAC"
PERCENT = Decimal("1.5")


def apply(amount: Decimal) -> Decimal:
    return amount * PERCENT / 100
