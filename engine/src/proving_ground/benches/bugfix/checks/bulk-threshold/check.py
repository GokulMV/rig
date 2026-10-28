import sys

sys.path.insert(0, "/app")
from shop.pricing import cart_total, line_total  # noqa: E402

assert round(line_total(1.0, 10), 2) == 9.5, line_total(1.0, 10)
assert round(line_total(1.0, 9), 2) == 9.0
assert round(line_total(2.0, 20), 2) == 38.0
assert round(cart_total([(1.0, 10)]), 2) == 9.5
