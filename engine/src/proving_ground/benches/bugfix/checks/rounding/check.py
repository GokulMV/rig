import sys

sys.path.insert(0, "/app")
from shop.pricing import cart_total  # noqa: E402

assert cart_total([(6.6666, 3)]) == 20.0, cart_total([(6.6666, 3)])
assert cart_total([(2.675, 1)]) == 2.68, cart_total([(2.675, 1)])
assert cart_total([(0.1, 1), (0.2, 1)]) == 0.3, cart_total([(0.1, 1), (0.2, 1)])
assert cart_total([(10.0, 1)], "SAVE10") == 9.0
