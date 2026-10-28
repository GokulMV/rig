"""Rounding to a currency's minor unit."""

from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

from ledger.currencies.registry import decimals


def to_minor(amount: Decimal, currency: str) -> Decimal:
    """Round half up to the currency's minor unit (cents, or whole yen)."""
    q = Decimal(1).scaleb(-decimals(currency))
    return amount.quantize(q, rounding=ROUND_HALF_UP)


def bankers(amount: Decimal, currency: str) -> Decimal:
    """Round half to even. Only for statistical reports, never for invoices."""
    q = Decimal(1).scaleb(-decimals(currency))
    return amount.quantize(q, rounding=ROUND_HALF_EVEN)
