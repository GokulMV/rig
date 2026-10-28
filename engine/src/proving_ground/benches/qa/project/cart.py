"""A shopping cart. Prices are integer cents."""

FREE_SHIPPING_FROM = 5000
SHIPPING = 499


class Cart:
    def __init__(self) -> None:
        self.items: dict[str, tuple[int, int]] = {}  # sku -> (price, qty)

    def add(self, sku: str, price: int, qty: int = 1) -> None:
        if qty < 1 or price < 0:
            raise ValueError("qty must be at least 1 and price not negative")
        _, have = self.items.get(sku, (price, 0))
        self.items[sku] = (price, have + qty)

    def remove(self, sku: str, qty: int = 1) -> None:
        if sku not in self.items:
            raise KeyError(sku)
        price, have = self.items[sku]
        if qty >= have:
            del self.items[sku]
        else:
            self.items[sku] = (price, have - qty)

    def subtotal(self) -> int:
        return sum(price * qty for price, qty in self.items.values())

    def shipping(self) -> int:
        if not self.items:
            return 0
        return 0 if self.subtotal() >= FREE_SHIPPING_FROM else SHIPPING

    def total(self) -> int:
        return self.subtotal() + self.shipping()
