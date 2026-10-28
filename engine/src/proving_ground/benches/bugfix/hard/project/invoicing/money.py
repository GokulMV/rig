"""Money helpers: minor units per currency and rounding to them. The rules are in README.md."""

from decimal import ROUND_HALF_UP, Decimal

MINOR_UNITS = {"JPY": 0, "KWD": 3}
DEFAULT_MINOR_UNITS = 2


def minor_units(currency: str) -> int:
    return MINOR_UNITS.get(currency, DEFAULT_MINOR_UNITS)


def to_minor(amount: str | Decimal, currency: str) -> int:
    """An exact amount in major units, rounded half up to whole minor units."""
    scaled = Decimal(amount).scaleb(minor_units(currency))
    return int(scaled.quantize(Decimal(1), rounding=ROUND_HALF_UP))
