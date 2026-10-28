"""Cart pricing: subtotals, bulk discounts, coupons."""

COUPONS = {"SAVE10": 0.10, "WELCOME5": 0.05}
BULK_QTY = 10
BULK_RATE = 0.05


def line_total(price: float, qty: int) -> float:
    total = price * qty
    if qty > BULK_QTY:
        total = total * (1 - BULK_RATE)
    return total


def cart_total(lines: list[tuple[float, int]], coupon: str | None = None) -> float:
    total = sum(line_total(price, qty) for price, qty in lines)
    if coupon in COUPONS:
        total = total * (1 - COUPONS[coupon])
    return total
