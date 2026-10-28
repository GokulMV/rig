"""Hard tier of the bugfix bench: the invoicing component, fixed to follow its README."""

MONEY = '''"""Money helpers: minor units per currency and rounding to them. The rules are in README.md."""

from decimal import ROUND_HALF_UP, Decimal, localcontext

MINOR_UNITS = {"JPY": 0, "KWD": 3, "BHD": 3}
DEFAULT_MINOR_UNITS = 2


def minor_units(currency: str) -> int:
    return MINOR_UNITS.get(currency, DEFAULT_MINOR_UNITS)


def to_minor(amount: str | Decimal, currency: str) -> int:
    """An exact amount in major units, rounded half up to whole minor units."""
    with localcontext() as ctx:
        ctx.prec = 200
        scaled = Decimal(amount).scaleb(minor_units(currency))
        return int(scaled.quantize(Decimal(1), rounding=ROUND_HALF_UP))
'''

INVOICE = '''"""Invoices: discounts, sharing the net out over the lines, and tax. Rules in README.md."""

from decimal import Decimal, localcontext
from fractions import Fraction

from money import to_minor


def _half_even(x: Fraction) -> int:
    return round(x)  # Fraction.__round__ with no digits rounds half to even


def build_invoice(
    lines: list[tuple[str, int, str]],
    currency: str,
    percent_off: str = "0",
    amount_off: str = "0",
) -> dict:
    with localcontext() as ctx:
        ctx.prec = 200
        amounts = [Decimal(price) * qty for price, qty, _ in lines]
        subtotal = sum(amounts, Decimal(0))
        discount = subtotal * Decimal(percent_off) / 100 + Decimal(amount_off)
        discount = min(discount, subtotal)
        net = to_minor(subtotal - discount, currency)

    if subtotal == 0:
        shares = [0] * len(lines)
    else:
        exact = [Fraction(net) * Fraction(a) / Fraction(subtotal) for a in amounts]
        shares = [int(e) for e in exact]  # exact shares are never negative: int() rounds down
        left = net - sum(shares)
        by_leftover = sorted(range(len(lines)), key=lambda i: (shares[i] - exact[i], i))
        for i in by_leftover[:left]:
            shares[i] += 1

    out = []
    for share, (_, _, rate) in zip(shares, lines):
        out.append((share, _half_even(Fraction(share) * Fraction(rate) / 100)))
    tax_total = sum(t for _, t in out)
    return {"lines": out, "net": net, "tax": tax_total, "total": net + tax_total}
'''

INSTALMENTS = '''"""Instalment plans: a total split into n payments, plus a fee. The rules are in README.md."""

from money import to_minor

MAX_INSTALMENTS = 24


def schedule(total: str, currency: str, n: int, fee: str = "0") -> list[int]:
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_INSTALMENTS:
        raise ValueError(f"instalments must be between 1 and {MAX_INSTALMENTS}, got {n!r}")
    amount = to_minor(total, currency)
    base, extra = divmod(amount, n)
    parts = [base + 1 if i < extra else base for i in range(n)]
    parts[0] += to_minor(fee, currency)
    return parts
'''

FIXED = {
    "invoicing/money.py": MONEY,
    "invoicing/invoice.py": INVOICE,
    "invoicing/instalments.py": INSTALMENTS,
}

SOLUTIONS = {
    ("bugfix", "hard-invoicing"): FIXED,
    ("bugfix", "hard-stale-test"): FIXED,
}
