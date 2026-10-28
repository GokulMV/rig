"""The text printed on shelf labels. Prices are whole cents (int)."""


def price(cents: int) -> str:
    """The label for one price: price(123456) == "€1.234,56"."""
    euros, rest = divmod(cents, 100)
    return f"€{euros:,}".replace(",", ".") + f",{rest:02d}"
