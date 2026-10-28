"""Invoice totals: lines, then the EUR processing fee (rule_17), rounded to the minor unit."""

from decimal import Decimal

from ledger.rules.registry import load
from ledger.util.rounding import to_minor


def invoice_total(lines: list[tuple[str, str]], currency: str) -> Decimal:
    """lines: (description, amount as text). Returns the total in `currency`."""
    subtotal = sum((Decimal(a) for _, a in lines), Decimal(0))
    total = to_minor(subtotal, currency)
    if currency == "EUR":
        total += load("rule_17").apply(subtotal)
    return total
