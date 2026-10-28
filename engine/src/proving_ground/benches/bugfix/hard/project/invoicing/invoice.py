"""Invoices: discounts, sharing the net out over the lines, and tax. Rules in README.md."""

from decimal import ROUND_HALF_UP, Decimal

from money import to_minor


def build_invoice(
    lines: list[tuple[str, int, str]],
    currency: str,
    percent_off: str = "0",
    amount_off: str = "0",
) -> dict:
    amounts = [Decimal(price) * qty for price, qty, _ in lines]
    subtotal = sum(amounts, Decimal(0))
    after_fixed = subtotal - Decimal(amount_off)
    discounted = after_fixed * Decimal(1 - float(percent_off) / 100)
    net = to_minor(discounted, currency)

    shares = [int((net * a / subtotal).quantize(Decimal(1), ROUND_HALF_UP)) for a in amounts]
    shares[-1] += net - sum(shares)  # so the lines add up to net

    out = []
    for share, (_, _, rate) in zip(shares, lines):
        tax = (Decimal(share) * Decimal(rate) / 100).quantize(Decimal(1), ROUND_HALF_UP)
        out.append((share, int(tax)))
    tax_total = sum(t for _, t in out)
    return {"lines": out, "net": net, "tax": tax_total, "total": net + tax_total}
