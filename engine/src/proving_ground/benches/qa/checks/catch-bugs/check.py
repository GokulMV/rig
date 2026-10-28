import sys

sys.path.insert(0, "/tests/checks/catch-bugs")
from mutants import check  # noqa: E402

check(
    {
        "add replaces instead of adding": ("have + qty", "qty"),
        "subtotal ignores quantity": ("price * qty for", "price for"),
        "negative price allowed": ("qty < 1 or price < 0", "qty < 1"),
        "shipping always charged": (
            "0 if self.subtotal() >= FREE_SHIPPING_FROM else SHIPPING",
            "SHIPPING",
        ),
    },
    need=4,
)
