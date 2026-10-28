import sys

sys.path.insert(0, "/tests/checks/edge-cases")
from mutants import check  # noqa: E402

check(
    {
        "threshold off by one": (
            "self.subtotal() >= FREE_SHIPPING_FROM",
            "self.subtotal() > FREE_SHIPPING_FROM",
        ),
        "empty cart charged shipping": (
            "if not self.items:\n            return 0",
            "if False:\n            return 0",
        ),
        "over-removal leaves negative qty": ("if qty >= have:", "if qty == have:"),
        "removing unknown sku is silent": ("            raise KeyError(sku)", "            return"),
    },
    need=4,
)
