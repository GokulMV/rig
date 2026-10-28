import sys

sys.path.insert(0, "/app")
from shop.pricing import cart_total  # noqa: E402

for code in ("save10", " SAVE10 ", "Save10"):
    assert round(cart_total([(10.0, 1)], code), 2) == 9.0, code
assert round(cart_total([(10.0, 1)], "nope"), 2) == 10.0
assert round(cart_total([(10.0, 1)], None), 2) == 10.0
